from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils.text import slugify
from rest_framework import serializers, status
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response

from laboratory.api.permissions import ReportAccessPermission
from laboratory.models import Report, SampleBatch
from laboratory.serializers.report_serializers import ReportCreateSerializer, ReportGenerateSerializer, ReportPublishSerializer, ReportReadSerializer, ReportUpdateSerializer
from laboratory.services.report_service import build_report_snapshot, create_report_version, generate_report_pdf, publish_report, render_report_html, report_queryset, require_report_access, require_superuser, update_report_draft
from laboratory.views.laboratory_views import LaboratoryPagination


class ReportBaseView(GenericAPIView):
    permission_classes = (ReportAccessPermission,)
    serializer_class = ReportReadSerializer
    pagination_class = LaboratoryPagination

    def get_queryset(self):
        queryset = report_queryset(self.request.user)
        if self.kwargs.get("batch_id"):
            queryset = queryset.filter(batch_id=self.kwargs["batch_id"])
        for parameter, field in (("farm", "batch__farm_id"), ("batch", "batch_id")):
            value = self.request.query_params.get(parameter)
            if value:
                value = serializers.UUIDField().run_validation(value)
                queryset = queryset.filter(**{field: value})
        if self.request.query_params.get("status"):
            queryset = queryset.filter(status=self.request.query_params["status"])
        for parameter, lookup in (("date_from", "batch__collected_at__gte"), ("date_to", "batch__collected_at__lte")):
            value = self.request.query_params.get(parameter)
            if value:
                queryset = queryset.filter(**{lookup: serializers.DateField().run_validation(value)})
        return queryset.order_by("-created_at", "id")

    def handle_exception(self, exc):
        if isinstance(exc, DjangoValidationError):
            exc = serializers.ValidationError(exc.message_dict if hasattr(exc, "message_dict") else exc.messages)
        return super().handle_exception(exc)

    def read(self, report, response_status=status.HTTP_200_OK):
        report = report_queryset(self.request.user).get(pk=report.pk)
        return Response(ReportReadSerializer(report).data, status=response_status)


class ReportListCreateView(ReportBaseView):
    def get(self, request, batch_id=None):
        page = self.paginate_queryset(self.get_queryset())
        return self.get_paginated_response(ReportReadSerializer(page, many=True).data)

    def post(self, request, batch_id=None):
        require_superuser(request.user)
        serializer = ReportCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        supplied_batch = data.get("batch")
        if batch_id and supplied_batch and batch_id != supplied_batch:
            raise serializers.ValidationError("O lote enviado difere do lote da URL.")
        batch_id = batch_id or supplied_batch
        if not batch_id:
            raise serializers.ValidationError({"batch": "Selecione um lote."})
        batch = get_object_or_404(SampleBatch, pk=batch_id)
        report = create_report_version(batch, data.get("analysis_revision"), request.user, data["title"])
        return self.read(report, status.HTTP_201_CREATED)


class ReportDetailView(ReportBaseView):
    def get(self, request, pk):
        return self.read(self.get_object())

    def patch(self, request, pk):
        serializer = ReportUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return self.read(update_report_draft(self.get_object(), serializer.validated_data, request.user))


class BatchReportDataView(ReportBaseView):
    def get(self, request, batch_id):
        require_superuser(request.user)
        batch = get_object_or_404(SampleBatch, pk=batch_id)
        report = Report.objects.filter(batch=batch).select_related("analysis_revision").order_by("-version").first()
        if request.query_params.get("report"):
            report = get_object_or_404(Report, pk=serializers.UUIDField().run_validation(request.query_params["report"]), batch=batch)
        if report is None:
            report = Report(batch=batch, title="Relatório de resultados")
        return Response(build_report_snapshot(report))


class ReportActionView(ReportBaseView):
    action = ""

    def post(self, request, pk):
        require_superuser(request.user)
        serializer_class = ReportPublishSerializer if self.action == "publish" else ReportGenerateSerializer
        serializer = serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        report = self.get_object()
        if self.action == "generate":
            report = generate_report_pdf(report, request.user)
        elif self.action == "publish":
            report = publish_report(report, request.user)
        elif self.action == "new-version":
            report = create_report_version(report.batch, report.analysis_revision, request.user, report.title)
        return self.read(report, status.HTTP_201_CREATED if self.action == "new-version" else status.HTTP_200_OK)


class ReportDownloadView(ReportBaseView):
    def get(self, request, pk):
        report = self.get_object()
        require_report_access(report, request.user)
        if not report.file:
            raise serializers.ValidationError("O PDF ainda não foi gerado.")
        farm_name = report.data_snapshot.get("farm", {}).get("name", report.batch.farm.name)
        filename = f"microbiological-report-{slugify(farm_name) or 'farm'}-batch-{slugify(report.data_snapshot.get('batch', {}).get('title', report.batch.title)) or 'lote'}-v{report.version}.pdf"
        return FileResponse(report.file.open("rb"), as_attachment=True, filename=filename, content_type="application/pdf")


class ReportPreviewView(ReportBaseView):
    def get(self, request, pk):
        report = self.get_object()
        snapshot = report.data_snapshot if report.status != Report.Status.DRAFT else build_report_snapshot(report)
        if not snapshot:
            raise serializers.ValidationError("Este relatório legado não possui snapshot. Baixe o PDF original ou crie uma nova versão.")
        response = HttpResponse(render_report_html(snapshot), content_type="text/html; charset=utf-8")
        response["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'; img-src data:"
        return response
