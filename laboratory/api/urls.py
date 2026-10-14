from django.urls import path

from laboratory.views import laboratory_views as views

app_name = "laboratory"

urlpatterns = [
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
    path("reports/", views.ReportListCreateView.as_view(), name="reports_list_create"),
    path("reports/<uuid:pk>/", views.ReportDetailView.as_view(), name="reports_detail"),
]
