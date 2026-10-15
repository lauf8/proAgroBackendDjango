from datetime import date

from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import FarmMembership, User
from laboratory.models import Analysis, Report, Sample, SampleBatch, SampleResult, SampleResultAnalysis
from laboratory.services import create_analysis_revision
from manage.models import Cow, Farm


class LaboratoryChainTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser("chain@lab.test", "Example123!", name="Laboratory")
        cls.member = User.objects.create_user("chain@farm.test", name="Member")
        cls.farm = Farm.objects.create(name="Own farm")
        cls.membership = FarmMembership.objects.create(user=cls.member, farm=cls.farm, role="viewer")
        cls.batch, cls.sample, cls.result = cls.records(cls.farm, "OWN")
        cls.other_batch, cls.other_sample, _ = cls.records(Farm.objects.create(name="Other farm"), "OTHER")

    @classmethod
    def records(cls, farm, title):
        cow = Cow.objects.create(farm=farm, name=f"Cow {title}", identifier=title)
        batch = SampleBatch.objects.create(farm=farm, title=title, collected_at=date(2026, 10, 1), created_by=cls.admin)
        sample = Sample.objects.create(batch=batch, cow=cow, sample_code=f"{title}-01", udder_quarter="left_front", notes="Sample notes")
        result = SampleResult.objects.create(sample=sample, result_type="positive", identified_name="Organism")
        SampleResultAnalysis.objects.create(sample_result=result, classification="subclinical", interpretation="Technical interpretation", recommendation="Professional notes", treatment_notes="Explicit private notes", created_by=cls.admin)
        SampleResult.objects.create(sample=sample, result_type="negative")
        analysis = Analysis.objects.create(batch=batch, created_by=cls.admin)
        create_analysis_revision(analysis=analysis, created_by=cls.admin, summary="First revision")
        revision = create_analysis_revision(analysis=analysis, created_by=cls.admin, summary="Current revision")
        for state in ("draft", "generated", "published", "cancelled"):
            Report.objects.create(batch=batch, analysis_revision=revision, title=f"Report {state}", status=state, created_by=cls.admin)
        return batch, sample, result

    def batch_url(self, batch=None):
        return reverse("laboratory:batch_chain", kwargs={"pk": (batch or self.batch).pk})

    def sample_url(self, sample=None):
        return reverse("laboratory:sample_chain", kwargs={"pk": (sample or self.sample).pk})

    def test_superuser_reads_complete_chain(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get(self.batch_url())
        self.assertEqual(response.status_code, 200)
        data = response.data
        self.assertEqual(data["title"], "OWN")
        self.assertEqual([sample["sample_code"] for sample in data["samples"]], ["OWN-01"])
        self.assertEqual(data["samples"][0]["cow_identifier"], "OWN")
        self.assertEqual({result["result_type"] for result in data["samples"][0]["results"]}, {"positive", "negative"})
        self.assertEqual(data["samples"][0]["results"][0]["technical_analysis"]["interpretation"], "Technical interpretation")
        self.assertEqual([revision["version"] for revision in data["analyses"][0]["revisions"]], [2, 1])
        self.assertEqual(len(data["reports"]), 4)

    def test_member_scope_excludes_foreign_records_and_private_assessments(self):
        self.client.force_authenticate(self.member)
        response = self.client.get(self.batch_url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual([report["status"] for report in response.data["reports"]], ["published"])
        for result in response.data["samples"][0]["results"]:
            self.assertNotIn("technical_analysis", result)
        self.assertEqual(self.client.get(self.batch_url(self.other_batch)).status_code, 404)
        self.assertEqual(self.client.get(self.sample_url(self.other_sample)).status_code, 404)

    def test_inactive_membership_and_anonymous_cannot_read_chain(self):
        self.membership.is_active = False
        self.membership.save()
        self.client.force_authenticate(self.member)
        for url in (self.batch_url(), self.sample_url()):
            self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_authenticate(None)
        for url in (self.batch_url(), self.sample_url()):
            self.assertEqual(self.client.get(url).status_code, 401)

    def test_sample_chain_contains_only_its_results(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get(self.sample_url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["sample_code"], "OWN-01")
        self.assertEqual(response.data["batch_title"], "OWN")
        self.assertEqual(response.data["results"][0]["id"], str(self.result.pk))

    def test_empty_batch_and_sample_are_supported(self):
        batch = SampleBatch.objects.create(farm=self.farm, title="Empty", collected_at=date(2026, 10, 1), created_by=self.admin)
        self.client.force_authenticate(self.admin)
        response = self.client.get(self.batch_url(batch))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["samples"], [])
        self.assertEqual(response.data["analyses"], [])
        self.assertEqual(response.data["reports"], [])
        sample = Sample.objects.create(batch=batch, cow=self.sample.cow, udder_quarter="composite", sample_code="EMPTY")
        self.assertEqual(self.client.get(self.sample_url(sample)).data["results"], [])

    def test_batch_chain_uses_bounded_queries(self):
        for index in range(5):
            cow = Cow.objects.create(farm=self.farm, name=f"Cow {index}", identifier=f"EXTRA-{index}")
            sample = Sample.objects.create(batch=self.batch, cow=cow, udder_quarter="composite", sample_code=f"EXTRA-{index}")
            SampleResult.objects.create(sample=sample, result_type="negative")
        self.client.force_authenticate(self.admin)
        with self.assertNumQueries(6):
            response = self.client.get(self.batch_url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["samples"]), 6)

    def test_chain_does_not_allow_writes(self):
        self.client.force_authenticate(self.admin)
        for url in (self.batch_url(), self.sample_url()):
            self.assertEqual(self.client.post(url, {}, format="json").status_code, 405)
            self.assertEqual(self.client.patch(url, {}, format="json").status_code, 405)
