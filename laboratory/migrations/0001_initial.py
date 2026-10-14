import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('manage', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Analysis',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('status', models.CharField(choices=[('draft', 'Draft'), ('under_review', 'Under review'), ('approved', 'Approved'), ('cancelled', 'Cancelled')], default='draft', max_length=12)),
                ('current_version', models.PositiveIntegerField(default=1)),
                ('approved_at', models.DateTimeField(blank=True, null=True)),
                ('approved_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='approved_analyses', to=settings.AUTH_USER_MODEL)),
                ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='created_analyses', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='AnalysisRevision',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('version', models.PositiveIntegerField()),
                ('summary', models.TextField(blank=True)),
                ('technical_notes', models.TextField(blank=True)),
                ('recommendations', models.TextField(blank=True)),
                ('analysis', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='revisions', to='laboratory.analysis')),
                ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='created_analysis_revisions', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-version'],
            },
        ),
        migrations.CreateModel(
            name='Microorganism',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(max_length=150, unique=True)),
                ('scientific_name', models.CharField(blank=True, max_length=150)),
                ('description', models.TextField(blank=True)),
                ('is_active', models.BooleanField(default=True)),
            ],
            options={
                'ordering': ['name'],
                'indexes': [models.Index(fields=['name', 'is_active'], name='microorganism_name_active_idx')],
            },
        ),
        migrations.CreateModel(
            name='SampleBatch',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('title', models.CharField(max_length=150)),
                ('collected_at', models.DateField()),
                ('received_at', models.DateField(blank=True, null=True)),
                ('status', models.CharField(choices=[('draft', 'Draft'), ('collected', 'Collected'), ('received', 'Received'), ('processing', 'Processing'), ('completed', 'Completed'), ('cancelled', 'Cancelled')], default='draft', max_length=10)),
                ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='created_sample_batches', to=settings.AUTH_USER_MODEL)),
                ('farm', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='sample_batches', to='manage.farm')),
            ],
            options={
                'ordering': ['-collected_at', '-created_at'],
            },
        ),
        migrations.CreateModel(
            name='Sample',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('udder_quarter', models.CharField(choices=[('left_front', 'Left front'), ('right_front', 'Right front'), ('left_rear', 'Left rear'), ('right_rear', 'Right rear'), ('composite', 'Composite')], max_length=11)),
                ('sample_code', models.CharField(max_length=100)),
                ('notes', models.TextField(blank=True)),
                ('cow', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='samples', to='manage.cow')),
                ('batch', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='samples', to='laboratory.samplebatch')),
            ],
        ),
        migrations.CreateModel(
            name='Report',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('title', models.CharField(max_length=150)),
                ('status', models.CharField(choices=[('draft', 'Draft'), ('generated', 'Generated'), ('published', 'Published'), ('cancelled', 'Cancelled')], default='draft', max_length=9)),
                ('file', models.FileField(blank=True, null=True, upload_to='reports/%Y/%m/')),
                ('generated_at', models.DateTimeField(blank=True, null=True)),
                ('analysis_revision', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='reports', to='laboratory.analysisrevision')),
                ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='created_reports', to=settings.AUTH_USER_MODEL)),
                ('batch', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='reports', to='laboratory.samplebatch')),
            ],
        ),
        migrations.AddField(
            model_name='analysis',
            name='batch',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='analyses', to='laboratory.samplebatch'),
        ),
        migrations.CreateModel(
            name='SampleResult',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('identified_name', models.CharField(blank=True, max_length=150)),
                ('result_type', models.CharField(choices=[('positive', 'Positive'), ('negative', 'Negative'), ('inconclusive', 'Inconclusive'), ('contaminated', 'Contaminated')], max_length=12)),
                ('severity', models.CharField(blank=True, choices=[('low', 'Low'), ('moderate', 'Moderate'), ('high', 'High')], max_length=8, null=True)),
                ('colony_count', models.PositiveIntegerField(blank=True, null=True)),
                ('notes', models.TextField(blank=True)),
                ('microorganism', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='sample_results', to='laboratory.microorganism')),
                ('sample', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='results', to='laboratory.sample')),
            ],
            options={
                'ordering': ['created_at'],
            },
        ),
        migrations.AddConstraint(
            model_name='analysisrevision',
            constraint=models.UniqueConstraint(fields=('analysis', 'version'), name='unique_analysis_revision_version'),
        ),
        migrations.AddIndex(
            model_name='samplebatch',
            index=models.Index(fields=['farm', 'status'], name='batch_farm_status_idx'),
        ),
        migrations.AddIndex(
            model_name='samplebatch',
            index=models.Index(fields=['farm', 'collected_at'], name='batch_farm_collected_idx'),
        ),
        migrations.AddIndex(
            model_name='sample',
            index=models.Index(fields=['batch', 'cow'], name='sample_batch_cow_idx'),
        ),
        migrations.AddConstraint(
            model_name='sample',
            constraint=models.UniqueConstraint(fields=('batch', 'sample_code'), name='unique_batch_sample_code'),
        ),
        migrations.AddConstraint(
            model_name='sample',
            constraint=models.UniqueConstraint(fields=('batch', 'cow', 'udder_quarter'), name='unique_batch_cow_quarter'),
        ),
        migrations.AddIndex(
            model_name='report',
            index=models.Index(fields=['batch', 'status'], name='report_batch_status_idx'),
        ),
        migrations.AddIndex(
            model_name='analysis',
            index=models.Index(fields=['batch', 'status'], name='analysis_batch_status_idx'),
        ),
        migrations.AddConstraint(
            model_name='sampleresult',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('result_type', 'positive'), _negated=True), ('microorganism__isnull', False), models.Q(('identified_name', ''), _negated=True), _connector='OR'), name='positive_result_has_organism'),
        ),
        migrations.AddConstraint(
            model_name='sampleresult',
            constraint=models.UniqueConstraint(condition=models.Q(('microorganism__isnull', False)), fields=('sample', 'microorganism'), name='unique_sample_microorganism'),
        ),
    ]
