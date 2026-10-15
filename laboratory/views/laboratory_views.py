from django.db.models import Q
from django.db.models.deletion import ProtectedError
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView
from rest_framework.pagination import PageNumberPagination

from laboratory.api.permissions import IsSuperUserOrReadOnly
from laboratory.serializers.sample_filters import SampleListQuerySerializer
from laboratory.models import Analysis, AnalysisRevision, Microorganism, Sample, SampleBatch, SampleResult
from laboratory.serializers.laboratory_serializers import (
    AnalysisSerializer, AnalysisRevisionSerializer, MicroorganismSerializer,
    SampleSerializer, SampleBatchSerializer, SampleResultSerializer,
)


class LaboratoryDeletionConflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Este registro possui vínculos protegidos e não pode ser excluído."
    default_code = "laboratory_has_related_records"


class LaboratoryPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class LaboratoryScopeMixin:
    permission_classes = (IsSuperUserOrReadOnly,)
    pagination_class = LaboratoryPagination

    def get_queryset(self):
        related = {
            SampleBatch: ("farm",), Sample: ("batch", "cow"),
            SampleResult: ("sample", "microorganism"), Analysis: ("batch",),
            AnalysisRevision: ("analysis__batch",),
        }
        queryset = self.model.objects.select_related(*related.get(self.model, ()))
        if not self.request.user.is_superuser:
            queryset = queryset.filter(**{
                f"{self.farm_path}__memberships__user": self.request.user,
                f"{self.farm_path}__memberships__is_active": True,
            }).distinct()
        return queryset.order_by("-created_at", "id")

    def perform_create(self, serializer):
        kwargs = {"created_by": self.request.user} if hasattr(self.model, "created_by") else {}
        serializer.save(**kwargs)

    def perform_destroy(self, instance):
        try:
            instance.delete()
        except ProtectedError as error:
            raise LaboratoryDeletionConflict() from error


class MicroorganismListCreateView(LaboratoryScopeMixin, ListCreateAPIView):
    model = Microorganism
    serializer_class = MicroorganismSerializer
    farm_path = "sample_results__sample__cow__farm"


class MicroorganismDetailView(LaboratoryScopeMixin, RetrieveUpdateDestroyAPIView):
    model = Microorganism
    serializer_class = MicroorganismSerializer
    farm_path = "sample_results__sample__cow__farm"


class SampleBatchListCreateView(LaboratoryScopeMixin, ListCreateAPIView):
    model = SampleBatch
    serializer_class = SampleBatchSerializer
    farm_path = "farm"


class SampleBatchDetailView(LaboratoryScopeMixin, RetrieveUpdateDestroyAPIView):
    model = SampleBatch
    serializer_class = SampleBatchSerializer
    farm_path = "farm"


class SampleListCreateView(LaboratoryScopeMixin, ListCreateAPIView):
    model = Sample
    serializer_class = SampleSerializer
    farm_path = "cow__farm"

    def get_queryset(self):
        queryset = super().get_queryset()
        query = SampleListQuerySerializer(data=self.request.query_params)
        query.is_valid(raise_exception=True)
        filters = query.validated_data
        if filters.get("farm"):
            queryset = queryset.filter(batch__farm_id=filters["farm"])
        if filters.get("cow"):
            queryset = queryset.filter(cow_id=filters["cow"])
        if filters.get("search"):
            queryset = queryset.filter(Q(cow__name__icontains=filters["search"]) | Q(cow__identifier__icontains=filters["search"]))
        return queryset.select_related("batch__farm")


class SampleDetailView(LaboratoryScopeMixin, RetrieveUpdateDestroyAPIView):
    model = Sample
    serializer_class = SampleSerializer
    farm_path = "cow__farm"


class SampleResultListCreateView(LaboratoryScopeMixin, ListCreateAPIView):
    model = SampleResult
    serializer_class = SampleResultSerializer
    farm_path = "sample__cow__farm"


class SampleResultDetailView(LaboratoryScopeMixin, RetrieveUpdateDestroyAPIView):
    model = SampleResult
    serializer_class = SampleResultSerializer
    farm_path = "sample__cow__farm"


class AnalysisListCreateView(LaboratoryScopeMixin, ListCreateAPIView):
    model = Analysis
    serializer_class = AnalysisSerializer
    farm_path = "batch__farm"


class AnalysisDetailView(LaboratoryScopeMixin, RetrieveUpdateDestroyAPIView):
    model = Analysis
    serializer_class = AnalysisSerializer
    farm_path = "batch__farm"


class AnalysisRevisionListCreateView(LaboratoryScopeMixin, ListCreateAPIView):
    model = AnalysisRevision
    serializer_class = AnalysisRevisionSerializer
    farm_path = "analysis__batch__farm"


class AnalysisRevisionDetailView(LaboratoryScopeMixin, RetrieveUpdateDestroyAPIView):
    model = AnalysisRevision
    serializer_class = AnalysisRevisionSerializer
    farm_path = "analysis__batch__farm"
