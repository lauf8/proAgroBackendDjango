from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from config.models import TimeStampedModel


class Microorganism(TimeStampedModel):
    name = models.CharField(max_length=150, unique=True)
    scientific_name = models.CharField(max_length=150, blank=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        indexes = [models.Index(fields=["name", "is_active"], name="microorganism_name_active_idx")]

    def __str__(self):
        return self.scientific_name or self.name


class SampleBatch(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        COLLECTED = "collected", "Collected"
        RECEIVED = "received", "Received"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    farm = models.ForeignKey("manage.Farm", on_delete=models.PROTECT, related_name="sample_batches")
    title = models.CharField(max_length=150)
    collected_at = models.DateField()
    received_at = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_sample_batches")

    class Meta:
        ordering = ["-collected_at", "-created_at"]
        indexes = [models.Index(fields=["farm", "status"], name="batch_farm_status_idx"), models.Index(fields=["farm", "collected_at"], name="batch_farm_collected_idx")]

    def clean(self):
        super().clean()
        if self.received_at and self.collected_at and self.received_at < self.collected_at:
            raise ValidationError({"received_at": "Receipt cannot precede collection."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class Sample(TimeStampedModel):
    class UdderQuarter(models.TextChoices):
        LEFT_FRONT = "left_front", "Left front"
        RIGHT_FRONT = "right_front", "Right front"
        LEFT_REAR = "left_rear", "Left rear"
        RIGHT_REAR = "right_rear", "Right rear"
        COMPOSITE = "composite", "Composite"

    batch = models.ForeignKey("laboratory.SampleBatch", on_delete=models.CASCADE, related_name="samples")
    cow = models.ForeignKey("manage.Cow", on_delete=models.PROTECT, related_name="samples")
    udder_quarter = models.CharField(max_length=11, choices=UdderQuarter.choices)
    sample_code = models.CharField(max_length=100)
    notes = models.TextField(blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["batch", "sample_code"], name="unique_batch_sample_code"), models.UniqueConstraint(fields=["batch", "cow", "udder_quarter"], name="unique_batch_cow_quarter")]
        indexes = [models.Index(fields=["batch", "cow"], name="sample_batch_cow_idx")]

    def clean(self):
        super().clean()
        if self.cow_id and self.batch_id and self.cow.farm_id != self.batch.farm_id:
            raise ValidationError({"cow": "The cow and batch must belong to the same farm."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.sample_code


class SampleResult(TimeStampedModel):
    class ResultType(models.TextChoices):
        POSITIVE = "positive", "Positive"
        NEGATIVE = "negative", "Negative"
        INCONCLUSIVE = "inconclusive", "Inconclusive"
        CONTAMINATED = "contaminated", "Contaminated"

    class Severity(models.TextChoices):
        LOW = "low", "Low"
        MODERATE = "moderate", "Moderate"
        HIGH = "high", "High"

    sample = models.ForeignKey("laboratory.Sample", on_delete=models.CASCADE, related_name="results")
    microorganism = models.ForeignKey("laboratory.Microorganism", on_delete=models.PROTECT, related_name="sample_results", null=True, blank=True)
    identified_name = models.CharField(max_length=150, blank=True)
    result_type = models.CharField(max_length=12, choices=ResultType.choices)
    severity = models.CharField(max_length=8, choices=Severity.choices, null=True, blank=True)
    colony_count = models.PositiveIntegerField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.CheckConstraint(condition=~models.Q(result_type="positive") | models.Q(microorganism__isnull=False) | ~models.Q(identified_name=""), name="positive_result_has_organism"),
            models.UniqueConstraint(fields=["sample", "microorganism"], condition=models.Q(microorganism__isnull=False), name="unique_sample_microorganism"),
        ]

    def clean(self):
        super().clean()
        if self.result_type == self.ResultType.POSITIVE and not self.microorganism_id and not self.identified_name.strip():
            raise ValidationError({"identified_name": "Positive results require an organism."})

    def save(self, *args, **kwargs):
        self.identified_name = self.identified_name.strip()
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.sample} - {self.result_type}"


class Analysis(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        UNDER_REVIEW = "under_review", "Under review"
        APPROVED = "approved", "Approved"
        CANCELLED = "cancelled", "Cancelled"

    batch = models.ForeignKey("laboratory.SampleBatch", on_delete=models.PROTECT, related_name="analyses")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    current_version = models.PositiveIntegerField(default=1)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_analyses")
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="approved_analyses", null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["batch", "status"], name="analysis_batch_status_idx")]

    def __str__(self):
        return f"{self.batch} - {self.id}"


class AnalysisRevision(TimeStampedModel):
    analysis = models.ForeignKey("laboratory.Analysis", on_delete=models.CASCADE, related_name="revisions")
    version = models.PositiveIntegerField()
    summary = models.TextField(blank=True)
    technical_notes = models.TextField(blank=True)
    recommendations = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_analysis_revisions")

    class Meta:
        ordering = ["-version"]
        constraints = [models.UniqueConstraint(fields=["analysis", "version"], name="unique_analysis_revision_version")]

    def save(self, *args, **kwargs):
        database = kwargs.get("using") or self._state.db or "default"
        with transaction.atomic(using=database):
            analysis = Analysis.objects.using(database).select_for_update().get(pk=self.analysis_id)
            if not self._state.adding or type(self).objects.using(database).filter(pk=self.pk).exists():
                raise ValidationError("Existing analysis revisions cannot be modified.")
            self.full_clean()
            result = super().save(*args, **kwargs)
            if analysis.current_version < self.version:
                analysis.current_version = self.version
                analysis.save(using=database, update_fields=["current_version", "updated_at"])
            return result

    def __str__(self):
        return f"{self.analysis} - v{self.version}"


class Report(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        GENERATED = "generated", "Generated"
        PUBLISHED = "published", "Published"
        CANCELLED = "cancelled", "Cancelled"

    batch = models.ForeignKey("laboratory.SampleBatch", on_delete=models.PROTECT, related_name="reports")
    analysis_revision = models.ForeignKey("laboratory.AnalysisRevision", on_delete=models.PROTECT, related_name="reports")
    title = models.CharField(max_length=150)
    status = models.CharField(max_length=9, choices=Status.choices, default=Status.DRAFT)
    file = models.FileField(upload_to="reports/%Y/%m/", null=True, blank=True)
    generated_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_reports")

    class Meta:
        indexes = [models.Index(fields=["batch", "status"], name="report_batch_status_idx")]

    def clean(self):
        super().clean()
        if self.analysis_revision_id and self.batch_id and self.analysis_revision.analysis.batch_id != self.batch_id:
            raise ValidationError({"analysis_revision": "The revision and report must belong to the same batch."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.title
