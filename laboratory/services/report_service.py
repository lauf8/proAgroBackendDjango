import base64
import mimetypes
from itertools import zip_longest
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Count, Max, Prefetch
from django.template.loader import render_to_string
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from laboratory.models import Analysis, AnalysisRevision, BatchCowAssessment, Report, Sample, SampleBatch, SampleResult, SampleResultAnalysis
from laboratory.services import create_analysis_revision

REVISION_FIELDS = ("summary", "technical_notes", "recommendations", "management_notes", "responsible_name", "professional_registration", "report_date")
RESULT_FIELDS = ("classification", "interpretation", "recommendation", "treatment_notes")
COW_FIELDS = ("clinical_status", "general_notes", "milking_group", "milking_position")


def require_superuser(user):
    if not user.is_authenticated or not user.is_active or not user.is_superuser:
        raise PermissionDenied("Somente superusuários podem alterar relatórios e análises.")


def report_queryset(user):
    queryset = Report.objects.select_related("batch__farm", "analysis_revision__analysis").annotate(animal_count=Count("batch__samples__cow", distinct=True))
    if not user.is_superuser:
        queryset = queryset.filter(status=Report.Status.PUBLISHED, batch__farm__memberships__user=user, batch__farm__memberships__is_active=True).distinct()
    return queryset


def require_report_access(report, user):
    if not user.is_authenticated or not user.is_active or not report_queryset(user).filter(pk=report.pk).exists():
        raise PermissionDenied("Você não tem acesso a este relatório.")


def load_batch(batch_id):
    return SampleBatch.objects.select_related("farm").prefetch_related(
        Prefetch("samples", queryset=Sample.objects.select_related("cow").order_by("cow__identifier", "sample_code").prefetch_related(
            Prefetch("results", queryset=SampleResult.objects.select_related("microorganism", "technical_analysis").order_by("created_at", "id"))
        )), "cow_assessments",
    ).get(pk=batch_id)


def laboratory_identity():
    identity = dict(settings.REPORT_LABORATORY)
    logo_path = settings.REPORT_LOGO_PATH
    identity["logo"] = ""
    if logo_path:
        path = Path(logo_path)
        content_type = mimetypes.guess_type(path.name)[0]
        if content_type not in ("image/png", "image/jpeg"):
            raise ValidationError("O logo deve ser um arquivo PNG ou JPEG local.")
        identity["logo"] = f"data:{content_type};base64,{base64.b64encode(path.read_bytes()).decode()}"
    return identity


def build_report_snapshot(report):
    batch = load_batch(report.batch_id)
    revision = AnalysisRevision.objects.get(pk=report.analysis_revision_id) if report.analysis_revision_id else AnalysisRevision()
    assessments = {str(item.cow_id): item for item in batch.cow_assessments.all()}
    animals = {}
    for sample in batch.samples.all():
        cow_id = str(sample.cow_id)
        assessment = assessments.get(cow_id)
        animal = animals.setdefault(cow_id, {
            "cow_id": cow_id, "identifier": sample.cow.identifier, "name": sample.cow.name,
            "udder_quarters": [], "microorganisms": [], "samples": [],
            **{field: getattr(assessment, field) if assessment else (None if field == "milking_position" else "") for field in COW_FIELDS},
        })
        animal["udder_quarters"].append(sample.udder_quarter)
        sample_data = {"id": str(sample.pk), "sample_code": sample.sample_code, "udder_quarter": sample.udder_quarter, "notes": sample.notes, "results": []}
        for result in sample.results.all():
            analysis = getattr(result, "technical_analysis", None)
            result_data = {
                "id": str(result.pk), "sample_id": str(sample.pk), "udder_quarter": sample.udder_quarter,
                "name": result.microorganism.name if result.microorganism else result.identified_name,
                "scientific_name": result.microorganism.scientific_name if result.microorganism else "",
                "result_type": result.result_type, "severity": result.severity, "colony_count": result.colony_count, "notes": result.notes,
                **{field: getattr(analysis, field) if analysis else "" for field in RESULT_FIELDS},
            }
            sample_data["results"].append(result_data)
            animal["microorganisms"].append(result_data)
        animal["samples"].append(sample_data)
    line = {group: [] for group in BatchCowAssessment.MilkingGroup.values}
    for animal in animals.values():
        if animal["milking_group"] in line:
            line[animal["milking_group"]].append({key: animal[key] for key in ("cow_id", "identifier", "name", "milking_position")})
    for group in line.values():
        group.sort(key=lambda item: (item["milking_position"] is None, item["milking_position"] or 0, item["identifier"]))
    return {
        "report": {"id": str(report.pk), "version": report.version, "title": report.title, "generated_at": (report.generated_at or timezone.now()).isoformat(), "report_date": str(revision.report_date or timezone.localdate())},
        "laboratory": laboratory_identity(),
        "farm": {"id": str(batch.farm_id), **{field: getattr(batch.farm, field) for field in ("name", "owner_name", "city", "state")}},
        "batch": {"id": str(batch.pk), "title": batch.title, "collected_at": str(batch.collected_at), "received_at": str(batch.received_at) if batch.received_at else "", "sample_count": sum(len(animal["samples"]) for animal in animals.values()), "animal_count": len(animals)},
        "responsible_professional": {"name": revision.responsible_name, "registration": revision.professional_registration, "contact": settings.REPORT_LABORATORY["contact"]},
        "animals": list(animals.values()), "milking_line": line,
        "general_analysis": {field: getattr(revision, field) for field in REVISION_FIELDS[:4]},
    }


def validate_report_data(report):
    snapshot = build_report_snapshot(report)
    if not snapshot["animals"] or not any(animal["microorganisms"] for animal in snapshot["animals"]):
        raise ValidationError("O lote não possui resultados microbiológicos para gerar o relatório.")
    if not all(sample["results"] for animal in snapshot["animals"] for sample in animal["samples"]):
        raise ValidationError("Todas as amostras precisam ter resultados registrados.")
    if not snapshot["responsible_professional"]["name"] or not snapshot["responsible_professional"]["registration"]:
        raise ValidationError("Informe o profissional responsável e o registro profissional.")
    if any(not animal["milking_group"] or not animal["clinical_status"] or any(not result["classification"] for result in animal["microorganisms"]) for animal in snapshot["animals"]):
        raise ValidationError("Preencha as análises individuais e a avaliação de cada vaca.")
    return snapshot


def render_report_html(snapshot):
    return render_to_string("reports/microbiological_report.html", {"data": snapshot, "milking_rows": list(zip_longest(*snapshot["milking_line"].values())), "css": render_to_string("reports/microbiological_report.css")})


def render_report_pdf(snapshot):
    from weasyprint import HTML
    def local_resource(url, *args, **kwargs):
        from weasyprint import default_url_fetcher
        if not url.startswith("data:image/"):
            raise ValueError("External resources are disabled.")
        return default_url_fetcher(url, *args, **kwargs)
    return HTML(string=render_report_html(snapshot), url_fetcher=local_resource).write_pdf()


@transaction.atomic
def create_report_version(batch, analysis_revision, user, title="Relatório de resultados"):
    require_superuser(user)
    batch = SampleBatch.objects.select_for_update().get(pk=batch.pk)
    if analysis_revision is None:
        analysis = Analysis.objects.create(batch=batch, created_by=user)
        analysis_revision = create_analysis_revision(analysis=analysis, created_by=user)
    if analysis_revision.analysis.batch_id != batch.pk:
        raise ValidationError("A revisão deve pertencer ao lote selecionado.")
    version = (Report.objects.filter(batch=batch).aggregate(value=Max("version"))["value"] or 0) + 1
    return Report.objects.create(batch=batch, analysis_revision=analysis_revision, version=version, title=title, created_by=user)


@transaction.atomic
def update_report_draft(report, data, user):
    require_superuser(user)
    report = Report.objects.select_for_update().select_related("analysis_revision__analysis", "batch").get(pk=report.pk)
    SampleBatch.objects.select_for_update().get(pk=report.batch_id)
    if report.status != Report.Status.DRAFT:
        raise ValidationError("Somente rascunhos podem ser alterados. Crie uma nova versão.")
    result_rows = data.get("result_analyses", [])
    cow_rows = data.get("cow_assessments", [])
    result_ids = [row["sample_result"] for row in result_rows]
    if len(set(result_ids)) != len(result_ids):
        raise ValidationError("Há resultados duplicados.")
    allowed_results = set(SampleResult.objects.filter(sample__batch=report.batch, pk__in=result_ids).values_list("pk", flat=True))
    if set(result_ids) != allowed_results:
        raise ValidationError("Os resultados devem pertencer ao lote do relatório.")
    cow_ids = [row["cow"] for row in cow_rows]
    if len(set(cow_ids)) != len(cow_ids) or set(cow_ids) != set(Sample.objects.filter(batch=report.batch, cow_id__in=cow_ids).values_list("cow_id", flat=True)):
        raise ValidationError("As vacas devem pertencer às amostras do lote e não podem se repetir.")
    existing_results = {item.sample_result_id: item for item in SampleResultAnalysis.objects.filter(sample_result_id__in=result_ids)}
    for row in result_rows:
        values = {key: value for key, value in row.items() if key in RESULT_FIELDS}
        existing = existing_results.get(row["sample_result"])
        if existing:
            for key, value in values.items():
                setattr(existing, key, value)
            existing.updated_by = user
            existing.save()
        else:
            SampleResultAnalysis.objects.create(sample_result_id=row["sample_result"], created_by=user, **values)
    existing_cows = {item.cow_id: item for item in BatchCowAssessment.objects.filter(batch=report.batch)}
    positions = {key: (value.milking_group, value.milking_position) for key, value in existing_cows.items()}
    positions.update({row["cow"]: (row["milking_group"], row.get("milking_position")) for row in cow_rows})
    occupied = [value for value in positions.values() if value[1] is not None]
    if len(set(occupied)) != len(occupied):
        raise ValidationError("Há posições duplicadas na linha de ordenha.")
    BatchCowAssessment.objects.filter(batch=report.batch, cow_id__in=cow_ids).update(milking_position=None)
    for row in cow_rows:
        values = {key: value for key, value in row.items() if key in COW_FIELDS}
        item = existing_cows.get(row["cow"])
        if item:
            for key, value in values.items():
                setattr(item, key, value)
            item.updated_by = user
            item.save()
        else:
            BatchCowAssessment.objects.create(batch=report.batch, cow_id=row["cow"], created_by=user, **values)
    if "general_analysis" in data:
        previous = report.analysis_revision
        values = {field: data["general_analysis"].get(field, getattr(previous, field)) for field in REVISION_FIELDS}
        if any(values[field] != getattr(previous, field) for field in REVISION_FIELDS):
            report.analysis_revision = create_analysis_revision(analysis=previous.analysis, created_by=user, **values)
    report.title = data.get("title", report.title)
    report.save()
    return report


@transaction.atomic
def generate_report_pdf(report, user):
    require_superuser(user)
    report = Report.objects.select_for_update().get(pk=report.pk)
    SampleBatch.objects.select_for_update().get(pk=report.batch_id)
    if report.status != Report.Status.DRAFT:
        raise ValidationError("Somente rascunhos podem gerar PDF. Crie uma nova versão.")
    report.generated_at = timezone.now()
    report.data_snapshot = validate_report_data(report)
    pdf = render_report_pdf(report.data_snapshot)
    report.file.save(f"microbiological-report-{report.pk}-v{report.version}.pdf", ContentFile(pdf), save=False)
    report.status = Report.Status.GENERATED
    try:
        report.save()
    except Exception:
        report.file.delete(save=False)
        raise
    return report


@transaction.atomic
def publish_report(report, user):
    require_superuser(user)
    report = Report.objects.select_for_update().get(pk=report.pk)
    if report.status != Report.Status.GENERATED or not report.file or not report.data_snapshot:
        raise ValidationError("Gere o PDF antes de publicar o relatório.")
    report.status = Report.Status.PUBLISHED
    report.published_at = timezone.now()
    report.published_by = user
    report.save()
    return report
