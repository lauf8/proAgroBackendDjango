from datetime import date

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import User
from laboratory.models import BatchCowAssessment, Sample, SampleBatch, SampleResult, SampleResultAnalysis
from laboratory.services.report_service import create_report_version, generate_report_pdf, update_report_draft
from manage.models import Cow, Farm


class Command(BaseCommand):
    help = "Create an explicit development-only microbiological report example."

    def add_arguments(self, parser):
        parser.add_argument("--user", required=True, help="Existing laboratory superuser email")

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Demo data requires DEBUG=True and must never be created in production.")
        user = User.objects.filter(email=options["user"], is_superuser=True, is_active=True).first()
        if user is None:
            raise CommandError("Select an existing active superuser.")
        farm = Farm.objects.create(name="Fazenda de demonstração", owner_name="Cliente de demonstração", city="Município de demonstração", state="BA")
        batch = SampleBatch.objects.create(farm=farm, title="Lote de demonstração", collected_at=date.today(), received_at=date.today(), created_by=user)
        for index, group in enumerate(("healthy", "subclinical", "clinical", "contagious", "contagious")):
            cow = Cow.objects.create(farm=farm, identifier=f"DEMO-{index + 1}", name=f"Vaca de demonstração {index + 1}")
            sample = Sample.objects.create(batch=batch, cow=cow, udder_quarter=Sample.UdderQuarter.values[index], sample_code=f"DEMO-{index + 1}", notes="Observação da amostra registrada pelo laboratório.")
            result_type = ("negative", "inconclusive", "positive", "positive", "contaminated")[index]
            result = SampleResult.objects.create(sample=sample, result_type=result_type, identified_name="Microrganismo de demonstração" if result_type == "positive" else "")
            SampleResultAnalysis.objects.create(sample_result=result, classification=group, interpretation="Texto ilustrativo preenchido para validação do relatório.", created_by=user)
            BatchCowAssessment.objects.create(batch=batch, cow=cow, clinical_status=group, milking_group=group, milking_position=2 if index == 4 else 1, general_notes="Observação consolidada de demonstração.", created_by=user)
            if index == 3:
                extra = Sample.objects.create(batch=batch, cow=cow, udder_quarter="left_front", sample_code="DEMO-EXTRA")
                for name in ("Microrganismo de demonstração A", "Microrganismo de demonstração B"):
                    result = SampleResult.objects.create(sample=extra, result_type="positive", identified_name=name, severity="high")
                    SampleResultAnalysis.objects.create(sample_result=result, classification=group, created_by=user)
        report = create_report_version(batch, None, user)
        report = update_report_draft(report, {"general_analysis": {"responsible_name": "Profissional de demonstração", "professional_registration": "Registro de demonstração", "summary": "Documento de teste. Dados fictícios para verificar paginação e caracteres em português.\n" * 100, "technical_notes": "Análises individuais preenchidas explicitamente para este exemplo.", "recommendations": "Campo destinado ao profissional responsável.", "management_notes": "Texto de demonstração para validação do layout."}}, user)
        report = generate_report_pdf(report, user)
        self.stdout.write(f"Report: {report.pk}\nStorage file: {report.file.name}\nPreview: /reports/{report.pk}\nBatch: /batches/{batch.pk}/report")
