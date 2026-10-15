from collections import Counter
from datetime import date, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import FarmMembership, User
from laboratory.models import Analysis, AnalysisRevision, BatchCowAssessment, Microorganism, Report, Sample, SampleBatch, SampleResult, SampleResultAnalysis
from laboratory.services.report_service import create_report_version, generate_report_pdf, publish_report, update_report_draft
from manage.models import Cow, Farm, MilkingLineGroup, MilkingLineItem


class Command(BaseCommand):
    help = "Replace local operational records with coherent fictional presentation data, preserving user accounts."

    def add_arguments(self, parser):
        parser.add_argument("--replace-operational-data", action="store_true", required=True)

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Presentation data replacement requires DEBUG=True.")
        user = User.objects.filter(is_superuser=True, is_active=True).first()
        if not user:
            raise CommandError("An active superuser is required.")
        files = [(report.file.storage, report.file.name) for report in Report.objects.exclude(file="").exclude(file=None)]
        for model in (Report, AnalysisRevision, Analysis, BatchCowAssessment, SampleResultAnalysis, SampleResult, Sample, SampleBatch, MilkingLineItem, MilkingLineGroup, Cow, FarmMembership, Farm, Microorganism):
            model.objects.all().delete()
        organisms = {name: Microorganism.objects.create(name=name, scientific_name=name) for name in ("Staphylococcus aureus", "Streptococcus agalactiae", "Escherichia coli", "Staphylococcus chromogenes")}
        names = (("Estrela", "Aurora", "Jasmim", "Safira", "Luna", "Brisa", "Pérola", "Amora"), ("Flor", "Canela", "Mel", "Violeta", "Serena", "Cristal"))
        farms = []
        reports = []
        today = date.today()
        for farm_index, (name, owner, city) in enumerate((("Fazenda Boa Esperança", "Marina Duarte", "Vitória da Conquista"), ("Sítio Vale do Leite", "Rafael Almeida", "Itapetinga"))):
            farm = Farm.objects.create(name=name, owner_name=owner, city=city, state="BA", notes="Cadastro fictício para apresentação da aplicação.")
            farms.append(farm)
            cows = [Cow.objects.create(farm=farm, name=cow_name, identifier=f"{farm_index + 1}{index + 1:03d}", breed="Girolando" if index % 2 == 0 else "Holandesa", birth_date=date(2021 + index % 3, 2 + index, 12)) for index, cow_name in enumerate(names[farm_index])]
            collected = today - timedelta(days=5 - farm_index * 2)
            batch = SampleBatch.objects.create(farm=farm, title=f"CML-{today.year}-{farm_index + 1:03d}", collected_at=collected, received_at=collected + timedelta(days=1), status="completed", created_by=user)
            positions = Counter()
            clinical_groups = ("healthy", "healthy", "subclinical", "clinical", "contagious", "contagious", "inconclusive", "inconclusive")
            for index, cow in enumerate(cows):
                classification = clinical_groups[index]
                group = "subclinical" if classification == "inconclusive" else classification
                positions[group] += 1
                BatchCowAssessment.objects.create(batch=batch, cow=cow, clinical_status=classification, milking_group=group, milking_position=positions[group], general_notes="Registro aguardando complementação da avaliação individual." if classification == "inconclusive" else "Avaliação individual registrada no acompanhamento deste lote.", created_by=user)
                sample = Sample.objects.create(batch=batch, cow=cow, udder_quarter=Sample.UdderQuarter.values[index % 5], sample_code=f"{batch.title}-{index + 1:02d}", notes="Amostra identificada individualmente e recebida sob refrigeração.")
                result_type = "negative" if index < 2 else "inconclusive" if index == 6 else "contaminated" if index == 7 else "positive"
                organism_name = ("Staphylococcus chromogenes", "Escherichia coli", "Staphylococcus aureus", "Streptococcus agalactiae")[(index - 2) % 4] if result_type == "positive" else None
                result = SampleResult.objects.create(sample=sample, result_type=result_type, microorganism=organisms[organism_name] if organism_name else None, severity="high" if group == "contagious" else "moderate" if result_type == "positive" else None)
                SampleResultAnalysis.objects.create(sample_result=result, classification=classification, interpretation="Não houve identificação de microrganismos nesta amostra." if result_type == "negative" else "O resultado não permite uma conclusão individual nesta etapa." if result_type in ("inconclusive", "contaminated") else f"Identificação de {organism_name} na amostra informada.", created_by=user)
                if index in (2, 4):
                    extra = Sample.objects.create(batch=batch, cow=cow, udder_quarter="left_rear" if index == 4 else "right_rear", sample_code=f"{batch.title}-{index + 1:02d}-B", notes="Segundo quarto mamário do mesmo animal.")
                    extra_result = SampleResult.objects.create(sample=extra, result_type="positive", microorganism=organisms["Staphylococcus chromogenes"])
                    SampleResultAnalysis.objects.create(sample_result=extra_result, classification=classification, interpretation="Identificação registrada separadamente por quarto mamário.", created_by=user)
            for group_index, (key, label, color) in enumerate((("healthy", "Sadias", "green"), ("subclinical", "Subclínicas", "orange"), ("clinical", "Clínicas", "red"), ("contagious", "Contagiosas", "darkred"))):
                group = MilkingLineGroup.objects.create(farm=farm, name=label, color=color, position=group_index)
                for assessment in batch.cow_assessments.filter(milking_group=key):
                    MilkingLineItem.objects.create(group=group, cow=assessment.cow, position=assessment.milking_position)
            report = create_report_version(batch, None, user)
            report = update_report_draft(report, {"general_analysis": {"summary": f"Consolidação dos resultados de {len(cows)} animais da {farm.name}, com amostras individualizadas por quarto mamário.", "technical_notes": "Base ilustrativa para apresentação da aplicação. Os dados não correspondem a coletas reais.\nResultados de amostras distintas são apresentados separadamente, inclusive quando pertencem ao mesmo animal.", "recommendations": "", "management_notes": "A linha de ordenha apresenta a organização informada para este lote. Posições e avaliações podem ser revisadas em uma nova versão.", "responsible_name": "Equipe técnica do laboratório", "professional_registration": "Simulação — sem validade profissional", "report_date": today}}, user)
            report = generate_report_pdf(report, user)
            if farm_index == 0:
                report = publish_report(report, user)
                create_report_version(batch, report.analysis_revision, user)
            reports.append(report)
        for member in User.objects.filter(is_superuser=False, is_active=True):
            FarmMembership.objects.create(user=member, farm=farms[0], role="owner")
        for storage, name in files:
            transaction.on_commit(lambda storage=storage, name=name: storage.delete(name))
        self.stdout.write(f"Created {len(farms)} farms, {Cow.objects.count()} cows, {Sample.objects.count()} samples and {Report.objects.count()} reports. User accounts preserved.")
        for report in reports:
            self.stdout.write(f"{report.batch.farm.name} | {report.batch.title} | {report.status} | /reports/{report.pk}")
