import uuid
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def number_existing_reports(apps, schema_editor):
    Report = apps.get_model("laboratory", "Report")
    batch_versions = {}
    for report in Report.objects.using(schema_editor.connection.alias).order_by("created_at", "id").iterator():
        version = batch_versions.get(report.batch_id, 0) + 1
        batch_versions[report.batch_id] = version
        Report.objects.using(schema_editor.connection.alias).filter(pk=report.pk).update(version=version)


class Migration(migrations.Migration):
    dependencies = [
        ("laboratory", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(model_name="analysisrevision", name="management_notes", field=models.TextField(blank=True)),
        migrations.AddField(model_name="analysisrevision", name="responsible_name", field=models.CharField(max_length=150, blank=True)),
        migrations.AddField(model_name="analysisrevision", name="professional_registration", field=models.CharField(max_length=100, blank=True)),
        migrations.AddField(model_name="analysisrevision", name="report_date", field=models.DateField(null=True, blank=True)),
        migrations.AddField(model_name="report", name="version", field=models.PositiveIntegerField(default=1)),
        migrations.AddField(model_name="report", name="data_snapshot", field=models.JSONField(default=dict, blank=True)),
        migrations.AddField(model_name="report", name="published_at", field=models.DateTimeField(null=True, blank=True)),
        migrations.AddField(model_name="report", name="published_by", field=models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.PROTECT, related_name="published_reports", null=True, blank=True)),
        migrations.RunPython(number_existing_reports, migrations.RunPython.noop),
        migrations.AddConstraint(model_name="report", constraint=models.UniqueConstraint(fields=["batch", "version"], name="unique_batch_report_version")),
        migrations.CreateModel(name="SampleResultAnalysis", fields=[
            ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
            ("created_at", models.DateTimeField(auto_now_add=True)),
            ("updated_at", models.DateTimeField(auto_now=True)),
            ("created_by", models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.PROTECT, related_name="created_%(class)s_records")),
            ("updated_by", models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.PROTECT, related_name="updated_%(class)s_records", null=True, blank=True)),
            ("sample_result", models.OneToOneField("laboratory.sampleresult", on_delete=django.db.models.deletion.CASCADE, related_name="technical_analysis")),
            ("classification", models.CharField(max_length=12, choices=[("healthy", "Healthy"), ("subclinical", "Subclinical"), ("clinical", "Clinical"), ("contagious", "Contagious"), ("inconclusive", "Inconclusive")])),
            ("interpretation", models.TextField(blank=True)),
            ("recommendation", models.TextField(blank=True)),
            ("treatment_notes", models.TextField(blank=True))
        ], options={"abstract": False}),
        migrations.CreateModel(name="BatchCowAssessment", fields=[
            ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
            ("created_at", models.DateTimeField(auto_now_add=True)),
            ("updated_at", models.DateTimeField(auto_now=True)),
            ("created_by", models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.PROTECT, related_name="created_%(class)s_records")),
            ("updated_by", models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.PROTECT, related_name="updated_%(class)s_records", null=True, blank=True)),
            ("batch", models.ForeignKey("laboratory.samplebatch", on_delete=django.db.models.deletion.PROTECT, related_name="cow_assessments")),
            ("cow", models.ForeignKey("manage.cow", on_delete=django.db.models.deletion.PROTECT, related_name="batch_assessments")),
            ("clinical_status", models.CharField(max_length=12, choices=[("healthy", "Healthy"), ("subclinical", "Subclinical"), ("clinical", "Clinical"), ("contagious", "Contagious"), ("inconclusive", "Inconclusive")])),
            ("general_notes", models.TextField(blank=True)),
            ("milking_group", models.CharField(max_length=12, choices=[("healthy", "Healthy"), ("subclinical", "Subclinical"), ("clinical", "Clinical"), ("contagious", "Contagious")])),
            ("milking_position", models.PositiveIntegerField(null=True, blank=True))
        ], options={"abstract": False}),
        migrations.AddConstraint(model_name="batchcowassessment", constraint=models.UniqueConstraint(fields=["batch", "cow"], name="unique_batch_cow_assessment")),
        migrations.AddConstraint(model_name="batchcowassessment", constraint=models.UniqueConstraint(fields=["batch", "milking_group", "milking_position"], condition=models.Q(milking_position__isnull=False), name="unique_batch_group_position")),
    ]
