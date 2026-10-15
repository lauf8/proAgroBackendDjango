from django.db.models import Prefetch
from rest_framework.generics import RetrieveAPIView

from laboratory.models import Analysis, Report, Sample, SampleBatch, SampleResult
from laboratory.serializers.chain_serializers import BatchChainSerializer, SampleChainSerializer
from laboratory.views.laboratory_views import LaboratoryScopeMixin


def chain_samples():
    return Sample.objects.select_related("cow", "batch").order_by("sample_code", "id").prefetch_related(
        Prefetch("results", queryset=SampleResult.objects.select_related("microorganism", "technical_analysis").order_by("created_at", "id"))
    )


class BatchChainView(LaboratoryScopeMixin, RetrieveAPIView):
    model = SampleBatch
    farm_path = "farm"
    serializer_class = BatchChainSerializer

    def get_queryset(self):
        reports = Report.objects.order_by("-version", "id")
        if not self.request.user.is_superuser:
            reports = reports.filter(status=Report.Status.PUBLISHED)
        return super().get_queryset().prefetch_related(
            Prefetch("samples", queryset=chain_samples()),
            Prefetch("analyses", queryset=Analysis.objects.order_by("-created_at", "id").prefetch_related("revisions")),
            Prefetch("reports", queryset=reports, to_attr="visible_reports"),
        )


class SampleChainView(LaboratoryScopeMixin, RetrieveAPIView):
    model = Sample
    farm_path = "batch__farm"
    serializer_class = SampleChainSerializer

    def get_queryset(self):
        return super().get_queryset().prefetch_related(
            Prefetch("results", queryset=SampleResult.objects.select_related("microorganism", "technical_analysis").order_by("created_at", "id"))
        )
