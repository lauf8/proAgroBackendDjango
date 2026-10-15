from rest_framework import serializers
from laboratory.models import AnalysisRevision, BatchCowAssessment, ClinicalClassification, Report


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        unknown = set(data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError({key: "Campo não permitido." for key in unknown})
        return super().to_internal_value(data)


class ReportReadSerializer(serializers.ModelSerializer):
    animal_count = serializers.IntegerField(read_only=True)
    farm = serializers.UUIDField(source="batch.farm_id", read_only=True)
    farm_name = serializers.CharField(source="batch.farm.name", read_only=True)
    batch_title = serializers.CharField(source="batch.title", read_only=True)
    collected_at = serializers.DateField(source="batch.collected_at", read_only=True)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        snapshot = instance.data_snapshot
        if snapshot:
            data["farm_name"] = snapshot["farm"]["name"]
            data["batch_title"] = snapshot["batch"]["title"]
            data["collected_at"] = snapshot["batch"]["collected_at"]
            data["animal_count"] = snapshot["batch"]["animal_count"]
        return data

    class Meta:
        model = Report
        exclude = ("file",)
        read_only_fields = tuple(field.name for field in Report._meta.fields)


class ReportCreateSerializer(StrictSerializer):
    batch = serializers.UUIDField(required=False)
    title = serializers.CharField(max_length=150, default="Relatório de resultados")
    analysis_revision = serializers.PrimaryKeyRelatedField(queryset=AnalysisRevision.objects.select_related("analysis"), required=False)


class SampleResultAnalysisSerializer(StrictSerializer):
    sample_result = serializers.UUIDField()
    classification = serializers.ChoiceField(choices=ClinicalClassification.choices)
    interpretation = serializers.CharField(allow_blank=True, default="")
    recommendation = serializers.CharField(allow_blank=True, default="")
    treatment_notes = serializers.CharField(allow_blank=True, default="")


class BatchCowAssessmentSerializer(StrictSerializer):
    cow = serializers.UUIDField()
    clinical_status = serializers.ChoiceField(choices=ClinicalClassification.choices)
    general_notes = serializers.CharField(allow_blank=True, default="")
    milking_group = serializers.ChoiceField(choices=BatchCowAssessment.MilkingGroup.choices)
    milking_position = serializers.IntegerField(min_value=1, allow_null=True, default=None)


class GeneralAnalysisSerializer(StrictSerializer):
    summary = serializers.CharField(allow_blank=True, required=False)
    technical_notes = serializers.CharField(allow_blank=True, required=False)
    recommendations = serializers.CharField(allow_blank=True, required=False)
    management_notes = serializers.CharField(allow_blank=True, required=False)
    responsible_name = serializers.CharField(max_length=150, allow_blank=True, required=False)
    professional_registration = serializers.CharField(max_length=100, allow_blank=True, required=False)
    report_date = serializers.DateField(allow_null=True, required=False)


class ReportUpdateSerializer(StrictSerializer):
    title = serializers.CharField(max_length=150, required=False)
    result_analyses = SampleResultAnalysisSerializer(many=True, required=False)
    cow_assessments = BatchCowAssessmentSerializer(many=True, required=False)
    general_analysis = GeneralAnalysisSerializer(required=False)


class ReportGenerateSerializer(StrictSerializer):
    pass


class ReportPublishSerializer(StrictSerializer):
    pass
