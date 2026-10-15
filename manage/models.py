from django.core.exceptions import ValidationError
from django.db import models
from config.models import TimeStampedModel


class Farm(TimeStampedModel):
    name = models.CharField(max_length=150)
    owner_name = models.CharField(max_length=150, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=2, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        indexes = [models.Index(fields=["name", "is_active"], name="farm_name_active_idx")]

    def __str__(self):
        return self.name


class Cow(TimeStampedModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        DRY = "dry", "Dry"
        SOLD = "sold", "Sold"
        DECEASED = "deceased", "Deceased"

    farm = models.ForeignKey("manage.Farm", on_delete=models.PROTECT, related_name="cows")
    name = models.CharField(max_length=100)
    identifier = models.CharField(max_length=100)
    birth_date = models.DateField(null=True, blank=True)
    breed = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["farm", "identifier"], name="unique_farm_cow_identifier")]
        indexes = [models.Index(fields=["farm", "status"], name="cow_farm_status_idx"), models.Index(fields=["farm", "name"], name="cow_farm_name_idx")]

    def __str__(self):
        return f"{self.identifier} - {self.name}"


class MilkingLineGroup(TimeStampedModel):
    farm = models.ForeignKey("manage.Farm", on_delete=models.PROTECT, related_name="milking_line_groups")
    name = models.CharField(max_length=100)
    color = models.CharField(max_length=30, blank=True)
    position = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["position"]
        constraints = [models.UniqueConstraint(fields=["farm", "name"], name="unique_farm_milking_group_name"), models.UniqueConstraint(fields=["farm", "position"], name="unique_farm_milking_group_pos")]

    def __str__(self):
        return f"{self.farm} - {self.name}"


class MilkingLineItem(TimeStampedModel):
    group = models.ForeignKey("manage.MilkingLineGroup", on_delete=models.CASCADE, related_name="items")
    cow = models.ForeignKey("manage.Cow", on_delete=models.PROTECT, related_name="milking_line_items")
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["position"]
        constraints = [models.UniqueConstraint(fields=["group", "cow"], name="unique_milking_group_cow"), models.UniqueConstraint(fields=["group", "position"], name="unique_milking_group_position")]

    def clean(self):
        super().clean()
        if self.cow_id and self.group_id and self.cow.farm_id != self.group.farm_id:
            raise ValidationError({"cow": "A vaca e o grupo devem pertencer à mesma fazenda."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.group} - {self.cow} - {self.position}"
