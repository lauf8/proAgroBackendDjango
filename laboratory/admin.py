from django.contrib import admin
from .models import Analysis, AnalysisRevision, Microorganism, Report, Sample, SampleBatch, SampleResult


@admin.register(Microorganism)
class MicroorganismAdmin(admin.ModelAdmin):
    list_display = ("name", "scientific_name", "is_active")
    search_fields = ("name", "scientific_name")
    list_filter = ("is_active",)


@admin.register(SampleBatch)
class SampleBatchAdmin(admin.ModelAdmin):
    list_display = ("title", "farm", "collected_at", "status")
    search_fields = ("title", "farm__name")
    list_filter = ("status", "farm")


@admin.register(Sample)
class SampleAdmin(admin.ModelAdmin):
    list_display = ("sample_code", "batch", "cow", "udder_quarter")
    search_fields = ("sample_code", "cow__identifier", "batch__title")
    list_filter = ("udder_quarter", "batch__farm")


@admin.register(SampleResult)
class SampleResultAdmin(admin.ModelAdmin):
    list_display = ("sample", "microorganism", "identified_name", "result_type", "severity")
    search_fields = ("sample__sample_code", "microorganism__name", "identified_name")
    list_filter = ("result_type", "severity")


@admin.register(Analysis)
class AnalysisAdmin(admin.ModelAdmin):
    list_display = ("id", "batch", "status", "current_version")
    search_fields = ("batch__title",)
    list_filter = ("status", "batch__farm")
    readonly_fields = ("current_version",)


@admin.register(AnalysisRevision)
class AnalysisRevisionAdmin(admin.ModelAdmin):
    list_display = ("analysis", "version", "created_by", "created_at")
    search_fields = ("analysis__batch__title", "summary")
    list_filter = ("analysis__batch__farm",)
    readonly_fields = tuple(field.name for field in AnalysisRevision._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ("title", "batch", "analysis_revision", "status")
    search_fields = ("title", "batch__title")
    list_filter = ("status", "batch__farm")
