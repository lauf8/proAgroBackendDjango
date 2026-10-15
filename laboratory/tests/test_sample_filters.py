from datetime import date

from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import FarmMembership, User
from laboratory.models import Sample, SampleBatch
from manage.models import Cow, Farm


class SampleFilterTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser("filter@lab.test", "Example123!", name="Lab")
        cls.member = User.objects.create_user("filter@farm.test", name="Member")
        cls.farm = Farm.objects.create(name="Boa Esperança")
        cls.other_farm = Farm.objects.create(name="Vale do Leite")
        cls.membership = FarmMembership.objects.create(user=cls.member, farm=cls.farm, role="viewer")
        cls.batch = SampleBatch.objects.create(farm=cls.farm, title="OWN", collected_at=date(2026, 10, 1), created_by=cls.admin)
        other_batch = SampleBatch.objects.create(farm=cls.other_farm, title="OTHER", collected_at=date(2026, 10, 1), created_by=cls.admin)
        cls.cow = Cow.objects.create(farm=cls.farm, name="Estrela", identifier="1001")
        cls.own_sample = Sample.objects.create(batch=cls.batch, cow=cls.cow, sample_code="OWN-1", udder_quarter="composite")
        cow = Cow.objects.create(farm=cls.farm, name="Aurora", identifier="1002")
        cls.second_sample = Sample.objects.create(batch=cls.batch, cow=cow, sample_code="OWN-2", udder_quarter="composite")
        cow = Cow.objects.create(farm=cls.other_farm, name="Estrela", identifier="1001")
        cls.other_sample = Sample.objects.create(batch=other_batch, cow=cow, sample_code="OTHER-1", udder_quarter="composite")

    def setUp(self):
        self.url = reverse("laboratory:samples_list_create")
        self.client.force_authenticate(self.admin)

    def ids(self, **filters):
        response = self.client.get(self.url, filters)
        self.assertEqual(response.status_code, 200, response.data)
        return {row["id"] for row in response.data["results"]}

    def test_filters_by_farm(self):
        self.assertEqual(self.ids(farm=self.farm.pk), {str(self.own_sample.pk), str(self.second_sample.pk)})
        self.assertEqual(self.ids(farm=self.other_farm.pk), {str(self.other_sample.pk)})

    def test_searches_cow_name_and_identifier_without_case_sensitivity(self):
        expected = {str(self.own_sample.pk), str(self.other_sample.pk)}
        self.assertEqual(self.ids(search="eStRe"), expected)
        self.assertEqual(self.ids(search="1001"), expected)
        self.assertEqual(self.ids(search="  Aurora  "), {str(self.second_sample.pk)})

    def test_combines_farm_cow_and_search_filters(self):
        self.assertEqual(self.ids(farm=self.farm.pk, search="Estrela"), {str(self.own_sample.pk)})
        self.assertEqual(self.ids(cow=self.cow.pk), {str(self.own_sample.pk)})
        self.assertEqual(self.ids(farm=self.other_farm.pk, cow=self.cow.pk), set())
        self.assertEqual(self.ids(farm=self.farm.pk, search="Missing cow"), set())

    def test_members_cannot_search_foreign_farms_or_cows(self):
        self.client.force_authenticate(self.member)
        self.assertEqual(self.ids(search="1001"), {str(self.own_sample.pk)})
        self.assertEqual(self.ids(farm=self.other_farm.pk), set())
        self.assertEqual(self.ids(cow=self.other_sample.cow_id), set())
        self.membership.is_active = False
        self.membership.save()
        self.assertEqual(self.ids(farm=self.farm.pk), set())

    def test_invalid_filters_have_validation_errors(self):
        for field in ("farm", "cow"):
            response = self.client.get(self.url, {field: "not-a-uuid"})
            self.assertEqual(response.status_code, 400)
            self.assertIn(field, response.data)
        self.assertEqual(self.client.get(self.url, {"search": "x" * 201}).status_code, 400)

    def test_filtered_pagination_and_farm_name_have_bounded_queries(self):
        for index in range(22):
            cow = Cow.objects.create(farm=self.farm, name=f"Estrela {index}", identifier=f"E-{index}")
            Sample.objects.create(batch=self.batch, cow=cow, sample_code=f"EXTRA-{index}", udder_quarter="composite")
        with self.assertNumQueries(2):
            response = self.client.get(self.url, {"farm": self.farm.pk, "search": "Estrela", "page_size": 20})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 23)
        self.assertEqual(len(response.data["results"]), 20)
        self.assertTrue(all(row["farm_name"] == self.farm.name for row in response.data["results"]))
        response = self.client.get(self.url, {"farm": self.farm.pk, "search": "Estrela", "page_size": 20, "page": 2})
        self.assertEqual(len(response.data["results"]), 3)

    def test_empty_search_preserves_unfiltered_listing(self):
        self.assertEqual(len(self.ids(search="")), 3)
