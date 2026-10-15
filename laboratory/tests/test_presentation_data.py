import tempfile
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import FarmMembership, User
from laboratory.models import Report, Sample, SampleBatch, SampleResultAnalysis
from manage.models import Cow, Farm


class PresentationDataTests(TestCase):
    def setUp(self):
        self.media = tempfile.TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        settings = override_settings(DEBUG=True, MEDIA_ROOT=self.media.name)
        settings.enable()
        self.addCleanup(settings.disable)
        self.admin = User.objects.create_superuser("presentation@lab.test", "Example123!", name="Laboratory")
        self.member = User.objects.create_user("presentation@farm.test", name="Member")
        self.old_farm = Farm.objects.create(name="Old farm")
        FarmMembership.objects.create(user=self.member, farm=self.old_farm, role="owner")

    def test_replacement_preserves_accounts_and_creates_coherent_records(self):
        call_command("reset_presentation_data", replace_operational_data=True, stdout=StringIO())
        self.assertEqual(User.objects.count(), 2)
        self.assertFalse(Farm.objects.filter(pk=self.old_farm.pk).exists())
        self.assertEqual((Farm.objects.count(), Cow.objects.count(), SampleBatch.objects.count(), Sample.objects.count()), (2, 14, 2, 18))
        self.assertEqual(set(Report.objects.values_list("status", flat=True)), {"draft", "generated", "published"})
        self.assertTrue(all(not item.treatment_notes and not item.recommendation for item in SampleResultAnalysis.objects.all()))
        for report in Report.objects.exclude(status="draft"):
            self.assertTrue(report.file.storage.exists(report.file.name))
            self.assertNotIn(str(report.batch_id), report.file.read().decode("latin1"))
            self.assertIn("não correspondem a coletas reais", report.data_snapshot["general_analysis"]["technical_notes"])
        client = APIClient()
        client.force_authenticate(self.member)
        response = client.get("/api/v1/farm-options/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["name"], "Fazenda Boa Esperança")
        self.assertEqual(client.get("/api/v1/laboratory/reports/").data["count"], 1)
        membership = FarmMembership.objects.get(user=self.member)
        membership.is_active = False
        membership.save()
        self.assertEqual(client.get("/api/v1/farm-options/").data["count"], 0)

    @override_settings(DEBUG=False)
    def test_replacement_refuses_production(self):
        with self.assertRaises(CommandError):
            call_command("reset_presentation_data", replace_operational_data=True, stdout=StringIO())
        self.assertTrue(Farm.objects.filter(pk=self.old_farm.pk).exists())
