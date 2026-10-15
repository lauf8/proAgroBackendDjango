from django.urls import path

from laboratory.views import laboratory_views as views

from laboratory.views import report_views
from laboratory.views.chain_views import BatchChainView, SampleChainView

app_name = "laboratory"

urlpatterns = [
    path("sample-batches/<uuid:pk>/chain/", BatchChainView.as_view(), name="batch_chain"),
    path("samples/<uuid:pk>/chain/", SampleChainView.as_view(), name="sample_chain"),
    path("batches/<uuid:batch_id>/report-data/", report_views.BatchReportDataView.as_view(), name="batch_report_data"),
    path("batches/<uuid:batch_id>/reports/", report_views.ReportListCreateView.as_view(), name="batch_reports"),
    path("reports/<uuid:pk>/generate/", report_views.ReportActionView.as_view(action="generate"), name="report_generate"),
    path("reports/<uuid:pk>/publish/", report_views.ReportActionView.as_view(action="publish"), name="report_publish"),
    path("reports/<uuid:pk>/new-version/", report_views.ReportActionView.as_view(action="new-version"), name="report_new_version"),
    path("reports/<uuid:pk>/download/", report_views.ReportDownloadView.as_view(), name="report_download"),
    path("reports/<uuid:pk>/preview/", report_views.ReportPreviewView.as_view(), name="report_preview"),
    path("microorganisms/", views.MicroorganismListCreateView.as_view(), name="microorganisms_list_create"),
    path("microorganisms/<uuid:pk>/", views.MicroorganismDetailView.as_view(), name="microorganisms_detail"),
    path("sample-batches/", views.SampleBatchListCreateView.as_view(), name="sample_batches_list_create"),
    path("sample-batches/<uuid:pk>/", views.SampleBatchDetailView.as_view(), name="sample_batches_detail"),
    path("samples/", views.SampleListCreateView.as_view(), name="samples_list_create"),
    path("samples/<uuid:pk>/", views.SampleDetailView.as_view(), name="samples_detail"),
    path("sample-results/", views.SampleResultListCreateView.as_view(), name="sample_results_list_create"),
    path("sample-results/<uuid:pk>/", views.SampleResultDetailView.as_view(), name="sample_results_detail"),
    path("analyses/", views.AnalysisListCreateView.as_view(), name="analyses_list_create"),
    path("analyses/<uuid:pk>/", views.AnalysisDetailView.as_view(), name="analyses_detail"),
    path("analysis-revisions/", views.AnalysisRevisionListCreateView.as_view(), name="analysis_revisions_list_create"),
    path("analysis-revisions/<uuid:pk>/", views.AnalysisRevisionDetailView.as_view(), name="analysis_revisions_detail"),
    path("reports/", report_views.ReportListCreateView.as_view(), name="reports_list_create"),
    path("reports/<uuid:pk>/", report_views.ReportDetailView.as_view(), name="reports_detail"),
]
