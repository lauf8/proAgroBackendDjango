from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework import serializers

from laboratory.models import Analysis, AnalysisRevision, Microorganism, Sample, SampleBatch, SampleResult
from laboratory.services import create_analysis_revision


class LaboratorySerializer(serializers.ModelSerializer):
    def save(self, **kwargs):
        try:
            with transaction.atomic():
                return super().save(**kwargs)
        except DjangoValidationError as error:
            detail = error.message_dict if hasattr(error, "message_dict") else error.messages
            raise serializers.ValidationError(detail) from error


class MicroorganismSerializer(LaboratorySerializer):
    class Meta:
        model = Microorganism
        fields = "__all__"
        read_only_fields = ("id", "created_at", "updated_at")


class SampleBatchSerializer(LaboratorySerializer):
    farm_name = serializers.CharField(source="farm.name", read_only=True)

    class Meta:
        model = SampleBatch
        fields = "__all__"
        read_only_fields = ("id", "created_at", "updated_at", "created_by")


class SampleSerializer(LaboratorySerializer):
    farm_name = serializers.CharField(source="batch.farm.name", read_only=True)
    cow_name = serializers.CharField(source="cow.name", read_only=True)
    cow_identifier = serializers.CharField(source="cow.identifier", read_only=True)
    batch_title = serializers.CharField(source="batch.title", read_only=True)

    class Meta:
        model = Sample
        fields = "__all__"
        read_only_fields = ("id", "created_at", "updated_at")


class SampleResultSerializer(LaboratorySerializer):
    sample_code = serializers.CharField(source="sample.sample_code", read_only=True)
    microorganism_name = serializers.CharField(source="microorganism.name", read_only=True, default="")

    class Meta:
        model = SampleResult
        fields = "__all__"
        read_only_fields = ("id", "created_at", "updated_at")


class AnalysisSerializer(LaboratorySerializer):
    batch_title = serializers.CharField(source="batch.title", read_only=True)

    class Meta:
        model = Analysis
        fields = "__all__"
        read_only_fields = ("id", "created_at", "updated_at", "created_by", "current_version")


class AnalysisRevisionSerializer(LaboratorySerializer):
    batch_title = serializers.CharField(source="analysis.batch.title", read_only=True)

    class Meta:
        model = AnalysisRevision
        fields = "__all__"
        read_only_fields = ("id", "created_at", "updated_at", "created_by", "version")

    def validate(self, attrs):
        if self.instance and attrs.get("analysis", self.instance.analysis) != self.instance.analysis:
            raise serializers.ValidationError({"analysis": "Uma revisão não pode ser transferida para outra análise."})
        return attrs

    def create(self, validated_data):
        return create_analysis_revision(**validated_data)

    def update(self, instance, validated_data):
        return create_analysis_revision(
            analysis=instance.analysis,
            created_by=self.context["request"].user,
            **{field: validated_data.get(field, getattr(instance, field))
               for field in ("summary", "technical_notes", "recommendations", "management_notes", "responsible_name", "professional_registration", "report_date")},
        )
