from rest_framework import serializers

from laboratory.models import Analysis, AnalysisRevision, Report, Sample, SampleBatch, SampleResult, SampleResultAnalysis


class ResultAnalysisReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = SampleResultAnalysis
        fields = ("classification", "interpretation", "recommendation", "treatment_notes")
        read_only_fields = fields


class ResultChainSerializer(serializers.ModelSerializer):
    microorganism_name = serializers.CharField(source="microorganism.name", read_only=True, default="")
    scientific_name = serializers.CharField(source="microorganism.scientific_name", read_only=True, default="")
    technical_analysis = ResultAnalysisReadSerializer(read_only=True)

    class Meta:
        model = SampleResult
        fields = ("id", "microorganism_name", "scientific_name", "identified_name", "result_type", "severity", "colony_count", "notes", "technical_analysis")
        read_only_fields = fields

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get("request")
        if not request or not request.user.is_superuser:
            fields.pop("technical_analysis")
        return fields


class SampleChainSerializer(serializers.ModelSerializer):
    cow_name = serializers.CharField(source="cow.name", read_only=True)
    cow_identifier = serializers.CharField(source="cow.identifier", read_only=True)
    batch_title = serializers.CharField(source="batch.title", read_only=True)
    results = ResultChainSerializer(many=True, read_only=True)

    class Meta:
        model = Sample
        fields = ("id", "sample_code", "batch_title", "udder_quarter", "notes", "cow_name", "cow_identifier", "results")
        read_only_fields = fields


class RevisionChainSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnalysisRevision
        fields = ("id", "version", "summary", "technical_notes", "recommendations", "management_notes", "responsible_name", "professional_registration", "report_date", "created_at")
        read_only_fields = fields


class AnalysisChainSerializer(serializers.ModelSerializer):
    revisions = RevisionChainSerializer(many=True, read_only=True)

    class Meta:
        model = Analysis
        fields = ("id", "status", "current_version", "revisions")
        read_only_fields = fields


class ReportChainSerializer(serializers.ModelSerializer):
    class Meta:
        model = Report
        fields = ("id", "title", "version", "status", "generated_at", "published_at")
        read_only_fields = fields


class BatchChainSerializer(serializers.ModelSerializer):
    farm_name = serializers.CharField(source="farm.name", read_only=True)
    samples = SampleChainSerializer(many=True, read_only=True)
    analyses = AnalysisChainSerializer(many=True, read_only=True)
    reports = ReportChainSerializer(source="visible_reports", many=True, read_only=True)

    class Meta:
        model = SampleBatch
        fields = ("id", "title", "farm_name", "status", "collected_at", "received_at", "samples", "analyses", "reports")
        read_only_fields = fields
