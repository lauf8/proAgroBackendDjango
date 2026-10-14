import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Farm',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(max_length=150)),
                ('owner_name', models.CharField(blank=True, max_length=150)),
                ('city', models.CharField(blank=True, max_length=100)),
                ('state', models.CharField(blank=True, max_length=2)),
                ('phone', models.CharField(blank=True, max_length=30)),
                ('notes', models.TextField(blank=True)),
                ('is_active', models.BooleanField(default=True)),
            ],
            options={
                'ordering': ['name'],
                'indexes': [models.Index(fields=['name', 'is_active'], name='farm_name_active_idx')],
            },
        ),
        migrations.CreateModel(
            name='Cow',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(max_length=100)),
                ('identifier', models.CharField(max_length=100)),
                ('birth_date', models.DateField(blank=True, null=True)),
                ('breed', models.CharField(blank=True, max_length=100)),
                ('status', models.CharField(choices=[('active', 'Active'), ('dry', 'Dry'), ('sold', 'Sold'), ('deceased', 'Deceased')], default='active', max_length=10)),
                ('notes', models.TextField(blank=True)),
                ('farm', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='cows', to='manage.farm')),
            ],
            options={
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='MilkingLineGroup',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(max_length=100)),
                ('color', models.CharField(blank=True, max_length=30)),
                ('position', models.PositiveIntegerField(default=0)),
                ('is_active', models.BooleanField(default=True)),
                ('farm', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='milking_line_groups', to='manage.farm')),
            ],
            options={
                'ordering': ['position'],
            },
        ),
        migrations.CreateModel(
            name='MilkingLineItem',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('position', models.PositiveIntegerField(default=0)),
                ('cow', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='milking_line_items', to='manage.cow')),
                ('group', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='manage.milkinglinegroup')),
            ],
            options={
                'ordering': ['position'],
            },
        ),
        migrations.AddIndex(
            model_name='cow',
            index=models.Index(fields=['farm', 'status'], name='cow_farm_status_idx'),
        ),
        migrations.AddIndex(
            model_name='cow',
            index=models.Index(fields=['farm', 'name'], name='cow_farm_name_idx'),
        ),
        migrations.AddConstraint(
            model_name='cow',
            constraint=models.UniqueConstraint(fields=('farm', 'identifier'), name='unique_farm_cow_identifier'),
        ),
        migrations.AddConstraint(
            model_name='milkinglinegroup',
            constraint=models.UniqueConstraint(fields=('farm', 'name'), name='unique_farm_milking_group_name'),
        ),
        migrations.AddConstraint(
            model_name='milkinglinegroup',
            constraint=models.UniqueConstraint(fields=('farm', 'position'), name='unique_farm_milking_group_pos'),
        ),
        migrations.AddConstraint(
            model_name='milkinglineitem',
            constraint=models.UniqueConstraint(fields=('group', 'cow'), name='unique_milking_group_cow'),
        ),
        migrations.AddConstraint(
            model_name='milkinglineitem',
            constraint=models.UniqueConstraint(fields=('group', 'position'), name='unique_milking_group_position'),
        ),
    ]
