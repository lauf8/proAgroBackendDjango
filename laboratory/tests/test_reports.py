import copy
import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db.models.deletion import ProtectedError
from django.test import override_settings
from django.urls import reverse
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APITestCase

from accounts.models import FarmMembership, User
from laboratory.models import BatchCowAssessment, Report, Sample, SampleBatch, SampleResult, SampleResultAnalysis
from laboratory.services.report_service import build_report_snapshot, create_report_version, generate_report_pdf, publish_report, update_report_draft
from manage.models import Cow, Farm


class ReportTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser("reports@lab.test", "ExamplePassword123!", name="Lab")
        cls.member = User.objects.create_user("reports@farm.test", name="Member")
        cls.farm = Farm.objects.create(name="Fazenda demonstração", owner_name="Cliente demonstração", city="Município", state="BA")
        cls.other_farm = Farm.objects.create(name="Other")
        cls.membership = FarmMembership.objects.create(user=cls.member, farm=cls.farm, role="viewer")
        cls.batch = SampleBatch.objects.create(farm=cls.farm, title="Lote de demonstração", collected_at=date(2026, 10, 1), received_at=date(2026, 10, 2), created_by=cls.admin)
        cls.cows = []
        for index, group in enumerate(("healthy", "subclinical", "clinical", "contagious", "contagious")):
            cow = Cow.objects.create(farm=cls.farm, identifier=f"D{index + 1}", name=f"Vaca {index + 1}")
            cls.cows.append(cow)
            sample = Sample.objects.create(batch=cls.batch, cow=cow, udder_quarter=("left_front", "right_front", "left_rear", "right_rear", "composite")[index], sample_code=f"S{index + 1}", notes="Observação da amostra.\nVerificar identificação.")
            result = SampleResult.objects.create(sample=sample, result_type=("negative", "inconclusive", "positive", "positive", "contaminated")[index], identified_name="Organismo de demonstração" if index in (2, 3) else "")
            SampleResultAnalysis.objects.create(sample_result=result, classification=group, interpretation="Interpretação informada pelo responsável.", created_by=cls.admin)
            BatchCowAssessment.objects.create(batch=cls.batch, cow=cow, clinical_status=group, general_notes="Observação consolidada.", milking_group=group, milking_position=2 if index == 4 else 1, created_by=cls.admin)
        sample = Sample.objects.create(batch=cls.batch, cow=cls.cows[3], udder_quarter="left_front", sample_code="S6")
        for name in ("Organismo A", "Organismo B"):
            result = SampleResult.objects.create(sample=sample, result_type="positive", identified_name=name, severity="high")
            SampleResultAnalysis.objects.create(sample_result=result, classification="contagious", created_by=cls.admin)

    def setUp(self):
        self.media = tempfile.TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        self.settings_override = override_settings(MEDIA_ROOT=self.media.name)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.report = create_report_version(self.batch, None, self.admin)
        self.report = update_report_draft(self.report, {"general_analysis": {"responsible_name": "Profissional demonstração", "professional_registration": "Registro demonstração", "summary": "Texto longo para verificar paginação e caracteres em português.\n" * 100, "management_notes": "Orientações preenchidas pelo responsável."}}, self.admin)
        self.client.force_authenticate(self.admin)

    def url(self, action=None, report=None):
        return reverse(f'laboratory:report_{action}' if action else 'laboratory:reports_detail', kwargs={"pk": (report or self.report).pk})

    def generated(self):
        self.report = generate_report_pdf(self.report, self.admin)
        return self.report

    def published(self):
        self.generated()
        self.report = publish_report(self.report, self.admin)
        return self.report

    def test_superuser_creates_draft(self):
        response = self.client.post(reverse("laboratory:batch_reports", kwargs={"batch_id": self.batch.pk}), {}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["status"], "draft")
        self.assertEqual(response.data["farm"], str(self.farm.pk))

    def test_common_user_cannot_create(self):
        self.client.force_authenticate(self.member)
        self.assertEqual(self.client.post(reverse("laboratory:batch_reports", kwargs={"batch_id": self.batch.pk}), {}, format="json").status_code, 403)
        with self.assertRaises(PermissionDenied):
            create_report_version(self.batch, None, self.member)

    def test_member_only_sees_own_published_reports(self):
        self.published()
        draft = create_report_version(self.batch, self.report.analysis_revision, self.admin)
        self.client.force_authenticate(self.member)
        response = self.client.get(reverse("laboratory:reports_list_create"))
        self.assertEqual([row["id"] for row in response.data["results"]], [str(self.report.pk)])
        self.assertEqual(self.client.get(self.url(report=draft)).status_code, 404)
        self.assertEqual(self.client.get(self.url()).status_code, 200)
        self.assertEqual(self.client.get(reverse("laboratory:reports_list_create"), {"farm": str(self.other_farm.pk)}).data["count"], 0)

    def test_no_membership_hides_detail_list_and_download(self):
        self.published()
        self.membership.is_active = False
        self.membership.save()
        self.client.force_authenticate(self.member)
        for suffix in (None, "download", "preview"):
            self.assertEqual(self.client.get(self.url(suffix)).status_code, 404)
        self.assertEqual(self.client.get(reverse("laboratory:reports_list_create")).data["count"], 0)

    def test_foreign_farm_hidden(self):
        self.published()
        outsider = User.objects.create_user("outsider@farm.test", name="Outsider")
        FarmMembership.objects.create(user=outsider, farm=self.other_farm, role="owner")
        self.client.force_authenticate(outsider)
        self.assertEqual(self.client.get(self.url()).status_code, 404)
        self.assertEqual(self.client.get(self.url("download")).status_code, 404)

    def test_result_analysis_can_be_updated(self):
        result = SampleResult.objects.filter(sample__batch=self.batch).first()
        response = self.client.patch(self.url(), {"result_analyses": [{"sample_result": str(result.pk), "classification": "clinical", "interpretation": "Revisão técnica", "recommendation": "Texto profissional", "treatment_notes": "Informado explicitamente"}]}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(SampleResultAnalysis.objects.get(sample_result=result).interpretation, "Revisão técnica")

    def test_only_superuser_changes_analysis(self):
        self.client.force_authenticate(self.member)
        self.assertEqual(self.client.patch(self.url(), {"result_analyses": []}, format="json").status_code, 403)
        with self.assertRaises(PermissionDenied):
            update_report_draft(self.report, {}, self.member)

    def test_assessment_validates_farm_and_preserves_cow(self):
        cow = Cow.objects.create(farm=self.other_farm, name="Other", identifier="X")
        with self.assertRaises(ValidationError):
            BatchCowAssessment.objects.create(batch=self.batch, cow=cow, clinical_status="healthy", milking_group="healthy", created_by=self.admin)
        with self.assertRaises(ProtectedError):
            self.cows[0].delete()

    def test_snapshot_structure_and_individual_analyses(self):
        snapshot = build_report_snapshot(self.report)
        self.assertEqual(snapshot["farm"]["name"], self.farm.name)
        self.assertEqual(snapshot["batch"]["animal_count"], 5)
        self.assertEqual(snapshot["batch"]["sample_count"], 6)
        self.assertEqual(len(snapshot["animals"][3]["microorganisms"]), 3)
        self.assertTrue(snapshot["animals"][0]["samples"][0]["notes"])
        self.assertEqual(snapshot["animals"][0]["microorganisms"][0]["classification"], "healthy")
        self.assertTrue(snapshot["animals"][0]["microorganisms"][0]["interpretation"])

    def test_snapshot_milking_line_order(self):
        line = build_report_snapshot(self.report)["milking_line"]
        self.assertEqual(set(line), {"healthy", "subclinical", "clinical", "contagious"})
        self.assertEqual([item["milking_position"] for item in line["contagious"]], [1, 2])

    def test_generation_creates_pdf_with_long_text(self):
        self.generated()
        self.assertEqual(self.report.status, "generated")
        with self.report.file.open("rb") as stream:
            self.assertEqual(stream.read(4), b"%PDF")
        self.assertTrue(self.report.generated_at)

    def test_published_report_immutable(self):
        stale_draft = Report.objects.get(pk=self.report.pk)
        self.published()
        with self.assertRaises(ValidationError):
            stale_draft.delete()
        self.report.title = "Changed"
        with self.assertRaises(ValidationError):
            self.report.save()
        self.assertEqual(self.client.patch(self.url(), {"title": "Changed"}, format="json").status_code, 400)
        self.assertEqual(self.client.post(self.url("generate"), {}, format="json").status_code, 400)
        self.assertEqual(self.client.delete(self.url()).status_code, 405)

    def test_current_data_changes_do_not_change_history(self):
        self.published()
        snapshot = copy.deepcopy(self.report.data_snapshot)
        original_file = self.report.file.name
        with self.report.file.open("rb") as stream:
            original_pdf = stream.read()
        cow = self.cows[0]
        cow.name = "New name"
        cow.save()
        result = SampleResult.objects.filter(sample__cow=cow).first()
        result.result_type = "inconclusive"
        result.save()
        self.report.refresh_from_db()
        self.assertEqual(self.report.data_snapshot, snapshot)
        self.assertEqual(self.report.file.name, original_file)
        with self.report.file.open("rb") as stream:
            self.assertEqual(stream.read(), original_pdf)
        with patch("laboratory.services.report_service.load_batch", side_effect=AssertionError("Live data used")):
            self.assertEqual(self.client.get(self.url("preview")).status_code, 200)

    def test_new_version_preserves_original(self):
        self.published()
        response = self.client.post(self.url("new_version"), {}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["version"], self.report.version + 1)
        self.assertEqual(response.data["status"], "draft")
        self.report.refresh_from_db()
        self.assertEqual(self.report.status, "published")

    def test_download_content_type_and_membership(self):
        self.published()
        self.client.force_authenticate(self.member)
        response = self.client.get(self.url("download"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("attachment;", response["Content-Disposition"])
        self.assertTrue(b"".join(response.streaming_content).startswith(b"%PDF"))

    def test_snapshot_query_count_is_bounded(self):
        with self.assertNumQueries(5):
            build_report_snapshot(self.report)

    def test_empty_batch_has_understandable_error(self):
        batch = SampleBatch.objects.create(farm=self.farm, title="Empty", collected_at=date.today(), created_by=self.admin)
        report = create_report_version(batch, None, self.admin)
        response = self.client.post(self.url("generate", report), {}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("não possui resultados", str(response.data))

    def test_duplicate_positions_rejected_and_swap_allowed(self):
        cows = self.cows[3:]
        rows = [{"cow": str(cow.pk), "clinical_status": "contagious", "milking_group": "contagious", "milking_position": 1} for cow in cows]
        self.assertEqual(self.client.patch(self.url(), {"cow_assessments": rows}, format="json").status_code, 400)
        rows[0]["milking_position"] = 2
        self.assertEqual(self.client.patch(self.url(), {"cow_assessments": rows}, format="json").status_code, 200)

    def test_all_result_types_preserved_without_generated_treatments(self):
        results = [result for animal in build_report_snapshot(self.report)["animals"] for result in animal["microorganisms"]]
        self.assertEqual({result["result_type"] for result in results}, {"positive", "negative", "inconclusive", "contaminated"})
        self.assertTrue(all(result["treatment_notes"] == "" and result["recommendation"] == "" for result in results))

    def test_client_cannot_assign_status_snapshot_file_or_farm(self):
        for key in ("status", "data_snapshot", "file", "farm_id", "analysis_revision"):
            self.assertEqual(self.client.patch(self.url(), {key: "arbitrary"}, format="json").status_code, 400)

    def test_member_cannot_generate_publish_or_create_version(self):
        self.published()
        self.client.force_authenticate(self.member)
        for action in ("generate", "publish", "new_version"):
            self.assertEqual(self.client.post(self.url(action), {}, format="json").status_code, 403)

    def test_publish_requires_generated_pdf(self):
        self.assertEqual(self.client.post(self.url("publish"), {}, format="json").status_code, 400)

    def test_generated_report_cannot_be_edited(self):
        self.generated()
        self.assertEqual(self.client.patch(self.url(), {"title": "Changed"}, format="json").status_code, 400)

    def test_batch_with_history_cannot_change_farm(self):
        self.batch.farm = self.other_farm
        with self.assertRaises(ValidationError):
            self.batch.save()
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.farm_id, self.farm.pk)
