from django.db import transaction
from django.db.models import Max
from .models import Analysis, AnalysisRevision


def create_analysis_revision(*, analysis, created_by, summary="", technical_notes="", recommendations=""):
    database = analysis._state.db or "default"
    with transaction.atomic(using=database):
        locked_analysis = Analysis.objects.using(database).select_for_update().get(pk=analysis.pk)
        latest_version = locked_analysis.revisions.aggregate(latest=Max("version"))["latest"] or 0
        version = max(latest_version, locked_analysis.current_version) + 1 if latest_version else locked_analysis.current_version
        revision = AnalysisRevision.objects.using(database).create(
            analysis=locked_analysis,
            version=version,
            created_by=created_by,
            summary=summary,
            technical_notes=technical_notes,
            recommendations=recommendations,
        )
        analysis.current_version = revision.version
        return revision
