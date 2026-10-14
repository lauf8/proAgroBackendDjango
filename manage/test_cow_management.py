import uuid
from datetime import date
from unittest.mock import patch

from django.db import IntegrityError, connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import FarmMembership, User
from laboratory.models import Sample, SampleBatch
from manage.models import Cow, Farm, MilkingLineGroup, MilkingLineItem
from manage.services.cow_service import create_cow, update_cow


class CowManagementFeatureTests(APITestCase):
    password = "StrongPassword123!"

    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser("admin@example.com", cls.password, name="Admin")
        cls.member = User.objects.create_user("member@example.com", cls.password, name="Member")
        cls.outsider = User.objects.create_user("outsider@example.com", cls.password, name="Outsider")
        cls.farm = Farm.objects.create(name="Farm")
        cls.other_farm = Farm.objects.create(name="Other farm")
        cls.membership = FarmMembership.objects.create(farm=cls.farm, user=cls.member, role="owner")
        cls.cow = Cow.objects.create(farm=cls.farm, name="Bella", identifier="A1")
        cls.other_cow = Cow.objects.create(farm=cls.other_farm, name="Other cow", identifier="A1")

    def setUp(self):
        self.list_url = self.collection_url(self.farm)
        self.detail_url = self.cow_url(self.farm, self.cow)
        self.payload = {
            "name": "Daisy", "identifier": "A2", "birth_date": "2022-05-01",
            "breed": "Holstein", "status": "active", "notes": "New cow",
        }
        self.authenticate(self.superuser)

    def collection_url(self, farm):
        return reverse("manage:cow_list_create", kwargs={"farm_id": farm.pk})

    def cow_url(self, farm, cow):
        return reverse("manage:cow_detail", kwargs={"farm_id": farm.pk, "cow_id": cow.pk})

    def authenticate(self, user):
        response = self.client.post(
            reverse("accounts:login"), {"email": user.email, "password": self.password}, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")

    def requests_for_scope(self, farm, cow):
        return (
            ("get", self.collection_url(farm), None),
            ("post", self.collection_url(farm), self.payload),
            ("get", self.cow_url(farm, cow), None),
            ("put", self.cow_url(farm, cow), self.payload),
            ("patch", self.cow_url(farm, cow), {"name": "Unauthorized"}),
            ("delete", self.cow_url(farm, cow), None),
        )

    def assert_scope_rejected(self, farm, cow, expected_status):
        for method, url, data in self.requests_for_scope(farm, cow):
            with self.subTest(method=method, url=url):
                response = getattr(self.client, method)(url, data=data, format="json")
                self.assertEqual(response.status_code, expected_status)
        cow.refresh_from_db()
        self.assertEqual(Cow.objects.count(), 2)

    def test_superuser_creates_cow(self):
        response = self.client.post(self.list_url, self.payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        cow = Cow.objects.get(pk=response.data["id"])
        self.assertEqual(cow.farm_id, self.farm.pk)
        self.assertEqual(cow.name, "Daisy")
        self.assertEqual(cow.birth_date, date(2022, 5, 1))
        self.assertEqual(cow.breed, "Holstein")
        self.assertEqual(cow.notes, "New cow")
        self.assertEqual(set(response.data), {
            "id", "farm", "name", "identifier", "birth_date", "breed", "status",
            "notes", "created_at", "updated_at",
        })
        self.assertEqual(response.data["farm"], self.farm.pk)

    def test_minimal_creation_uses_defaults(self):
        response = self.client.post(self.list_url, {"name": "Daisy", "identifier": "A2"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        cow = Cow.objects.get(pk=response.data["id"])
        self.assertEqual(cow.status, Cow.Status.ACTIVE)
        self.assertIsNone(cow.birth_date)
        self.assertEqual(cow.breed, "")
        self.assertEqual(cow.notes, "")

    def test_list_is_scoped_to_farm(self):
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], str(self.cow.pk))
        self.assertNotIn(str(self.other_cow.pk), response.content.decode())

    def test_retrieve_cow(self):
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], str(self.cow.pk))
        self.assertEqual(response.data["identifier"], "A1")

    def test_partial_update(self):
        response = self.client.patch(self.detail_url, {"name": "Updated", "status": "dry"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.cow.refresh_from_db()
        self.assertEqual(self.cow.name, "Updated")
        self.assertEqual(self.cow.status, Cow.Status.DRY)
        self.assertEqual(self.cow.identifier, "A1")

    def test_full_update(self):
        response = self.client.put(self.detail_url, self.payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.cow.refresh_from_db()
        self.assertEqual(self.cow.name, self.payload["name"])
        self.assertEqual(self.cow.identifier, self.payload["identifier"])
        self.assertEqual(self.cow.birth_date, date(2022, 5, 1))

    def test_delete_cow_without_dependencies(self):
        response = self.client.delete(self.detail_url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(response.content, b"")
        self.assertFalse(Cow.objects.filter(pk=self.cow.pk).exists())
        self.assertTrue(Farm.objects.filter(pk=self.farm.pk).exists())
        self.assertTrue(Cow.objects.filter(pk=self.other_cow.pk).exists())

    def test_active_member_can_perform_bread_for_every_role(self):
        self.authenticate(self.member)
        for role in FarmMembership.Role.values:
            with self.subTest(role=role):
                self.membership.role = role
                self.membership.save(update_fields=["role"])
                self.assertEqual(self.client.get(self.list_url).status_code, status.HTTP_200_OK)
                response = self.client.post(self.list_url, self.payload, format="json")
                self.assertEqual(response.status_code, status.HTTP_201_CREATED)
                cow = Cow.objects.get(pk=response.data["id"])
                url = self.cow_url(self.farm, cow)
                self.assertEqual(self.client.get(url).status_code, status.HTTP_200_OK)
                self.assertEqual(self.client.put(url, self.payload, format="json").status_code, status.HTTP_200_OK)
                self.assertEqual(self.client.patch(url, {"notes": "Updated"}, format="json").status_code, status.HTTP_200_OK)
                self.assertEqual(self.client.delete(url).status_code, status.HTTP_204_NO_CONTENT)

    def test_user_without_membership_is_forbidden(self):
        for is_staff in (False, True):
            with self.subTest(is_staff=is_staff):
                self.outsider.is_staff = is_staff
                self.outsider.save(update_fields=["is_staff"])
                self.authenticate(self.outsider)
                self.assert_scope_rejected(self.farm, self.cow, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.cow.name, "Bella")

    def test_membership_on_another_farm_does_not_grant_access(self):
        self.authenticate(self.member)
        self.assert_scope_rejected(self.other_farm, self.other_cow, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.other_cow.name, "Other cow")

    def test_inactive_membership_is_forbidden(self):
        self.authenticate(self.member)
        self.membership.is_active = False
        self.membership.save(update_fields=["is_active"])
        self.assert_scope_rejected(self.farm, self.cow, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_and_invalid_tokens_are_rejected(self):
        for authorization in (None, "Bearer invalid-token"):
            with self.subTest(authorization=authorization):
                self.client.credentials(**({"HTTP_AUTHORIZATION": authorization} if authorization else {}))
                self.assert_scope_rejected(self.farm, self.cow, status.HTTP_401_UNAUTHORIZED)

    def test_inactive_user_is_rejected(self):
        self.authenticate(self.member)
        self.member.is_active = False
        self.member.save(update_fields=["is_active"])
        self.assert_scope_rejected(self.farm, self.cow, status.HTTP_401_UNAUTHORIZED)

    def test_membership_revocation_takes_effect_with_existing_token(self):
        self.authenticate(self.member)
        self.assertEqual(self.client.get(self.detail_url).status_code, status.HTTP_200_OK)
        self.membership.is_active = False
        self.membership.save(update_fields=["is_active"])
        response = self.client.patch(self.detail_url, {"name": "Unauthorized"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.cow.refresh_from_db()
        self.assertEqual(self.cow.name, "Bella")

    def test_cow_from_other_farm_is_not_accessible_through_authorized_farm(self):
        self.authenticate(self.member)
        url = self.cow_url(self.farm, self.other_cow)
        for method in ("get", "put", "patch", "delete"):
            with self.subTest(method=method):
                response = getattr(self.client, method)(url, data=self.payload if method in ("put", "patch") else None, format="json")
                self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.other_cow.refresh_from_db()
        self.assertEqual(self.other_cow.name, "Other cow")

    def test_farm_and_audit_fields_cannot_be_controlled(self):
        payload = {
            **self.payload, "farm": str(self.other_farm.pk), "farm_id": str(self.other_farm.pk),
            "id": str(uuid.uuid4()), "created_at": "2000-01-01T00:00:00Z",
            "updated_at": "2000-01-01T00:00:00Z",
        }
        response = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        cow = Cow.objects.get(pk=response.data["id"])
        self.assertEqual(cow.farm_id, self.farm.pk)
        self.assertNotEqual(str(cow.pk), payload["id"])
        self.assertNotEqual(cow.created_at.year, 2000)
        original_created_at = cow.created_at
        response = self.client.patch(self.cow_url(self.farm, cow), payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        cow.refresh_from_db()
        self.assertEqual(cow.farm_id, self.farm.pk)
        self.assertEqual(cow.created_at, original_created_at)
        self.assertNotEqual(cow.updated_at.year, 2000)

    def test_required_fields_for_create_and_full_update(self):
        for field in ("name", "identifier"):
            payload = {key: value for key, value in self.payload.items() if key != field}
            for method, url in (("post", self.list_url), ("put", self.detail_url)):
                with self.subTest(field=field, method=method):
                    response = getattr(self.client, method)(url, payload, format="json")
                    self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                    self.assertIn(field, response.data)
        self.assertEqual(Cow.objects.count(), 2)

    def test_invalid_fields_are_rejected_without_updates(self):
        for field, value in (
            ("name", ""), ("identifier", ""), ("identifier", "A" * 101),
            ("status", "invalid"), ("birth_date", "invalid-date"),
        ):
            for method, url in (("post", self.list_url), ("patch", self.detail_url)):
                with self.subTest(field=field, method=method):
                    response = getattr(self.client, method)(url, {**self.payload, field: value}, format="json")
                    self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                    self.assertIn(field, response.data)
        self.cow.refresh_from_db()
        self.assertEqual(self.cow.name, "Bella")
        self.assertEqual(Cow.objects.count(), 2)

    def test_nullable_birth_date_can_be_cleared(self):
        self.cow.birth_date = date(2022, 5, 1)
        self.cow.save(update_fields=["birth_date"])
        response = self.client.patch(self.detail_url, {"birth_date": None}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.cow.refresh_from_db()
        self.assertIsNone(self.cow.birth_date)

    def test_all_status_choices_are_accepted(self):
        for cow_status in Cow.Status.values:
            with self.subTest(status=cow_status):
                response = self.client.patch(self.detail_url, {"status": cow_status}, format="json")
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.cow.refresh_from_db()
                self.assertEqual(self.cow.status, cow_status)

    def test_duplicate_identifier_on_create(self):
        response = self.client.post(self.list_url, {**self.payload, "identifier": "A1"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("identifier", response.data)
        self.assertEqual(Cow.objects.count(), 2)

    def test_duplicate_identifier_on_update(self):
        Cow.objects.create(farm=self.farm, name="Daisy", identifier="A2")
        response = self.client.patch(self.detail_url, {"identifier": "A2", "name": "Unauthorized"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.cow.refresh_from_db()
        self.assertEqual(self.cow.identifier, "A1")
        self.assertEqual(self.cow.name, "Bella")

    def test_unchanged_identifier_is_allowed(self):
        response = self.client.patch(self.detail_url, {"identifier": "A1"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_same_identifier_is_allowed_on_different_farms(self):
        payload = {**self.payload, "identifier": "A3"}
        for farm in (self.farm, self.other_farm):
            response = self.client.post(self.collection_url(farm), payload, format="json")
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Cow.objects.filter(identifier="A3").count(), 2)

    def test_duplicate_insert_after_validation_returns_field_error(self):
        def competing_creation(*, farm, cow_data):
            Cow.objects.create(farm=farm, name="Competing cow", identifier=cow_data["identifier"])
            return create_cow(farm=farm, cow_data=cow_data)

        with patch("manage.api.cow_serializers.create_cow", side_effect=competing_creation):
            response = self.client.post(self.list_url, self.payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("identifier", response.data)
        self.assertEqual(Cow.objects.filter(farm=self.farm, identifier="A2").count(), 1)

    def test_duplicate_update_after_validation_rolls_back_changes(self):
        def competing_update(*, cow, cow_data):
            Cow.objects.create(farm=cow.farm, name="Competing cow", identifier=cow_data["identifier"])
            return update_cow(cow=cow, cow_data=cow_data)

        with patch("manage.api.cow_serializers.update_cow", side_effect=competing_update):
            response = self.client.patch(self.detail_url, {"name": "Changed", "identifier": "A2"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.cow.refresh_from_db()
        self.assertEqual(self.cow.name, "Bella")
        self.assertEqual(self.cow.identifier, "A1")

    def test_unrelated_database_errors_are_not_hidden(self):
        with patch("manage.api.cow_serializers.create_cow", side_effect=IntegrityError("Unexpected failure")), self.assertRaises(IntegrityError):
            self.client.post(self.list_url, self.payload, format="json")
        self.assertEqual(Cow.objects.count(), 2)

    def test_delete_with_sample_returns_conflict_and_preserves_history(self):
        batch = SampleBatch.objects.create(
            farm=self.farm, title="Batch", collected_at=date(2026, 10, 1), created_by=self.superuser,
        )
        sample = Sample.objects.create(batch=batch, cow=self.cow, udder_quarter="composite", sample_code="S1")
        response = self.client.delete(self.detail_url)
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertIn("detail", response.data)
        self.assertTrue(Cow.objects.filter(pk=self.cow.pk).exists())
        self.assertTrue(Sample.objects.filter(pk=sample.pk, cow=self.cow).exists())
        self.assertTrue(SampleBatch.objects.filter(pk=batch.pk).exists())

    def test_delete_with_milking_item_returns_conflict(self):
        group = MilkingLineGroup.objects.create(farm=self.farm, name="Group")
        item = MilkingLineItem.objects.create(group=group, cow=self.cow)
        response = self.client.delete(self.detail_url)
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertTrue(Cow.objects.filter(pk=self.cow.pk).exists())
        self.assertTrue(MilkingLineItem.objects.filter(pk=item.pk).exists())

    def test_empty_list_and_pagination(self):
        farm = Farm.objects.create(name="Empty farm")
        response = self.client.get(self.collection_url(farm))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["results"], [])
        Cow.objects.create(farm=self.farm, name="Daisy", identifier="A2")
        response = self.client.get(self.list_url, {"page_size": 1})
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertIsNotNone(response.data["next"])
        second = self.client.get(self.list_url, {"page_size": 1, "page": 2})
        self.assertEqual(second.data["results"][0]["name"], "Daisy")

    def test_filter_by_status_and_search(self):
        Cow.objects.create(farm=self.farm, name="Daisy", identifier="B2", status="dry")
        for query, expected_name in (
            ({"status": "active"}, "Bella"), ({"status": "dry"}, "Daisy"),
            ({"search": "BEL"}, "Bella"), ({"search": "b2"}, "Daisy"),
            ({"search": "daisy", "status": "dry"}, "Daisy"),
        ):
            with self.subTest(query=query):
                response = self.client.get(self.list_url, query)
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.assertEqual(response.data["count"], 1)
                self.assertEqual(response.data["results"][0]["name"], expected_name)
        response = self.client.get(self.list_url, {"search": "missing"})
        self.assertEqual(response.data["results"], [])

    def test_invalid_status_filter(self):
        response = self.client.get(self.list_url, {"status": "invalid"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("status", response.data)

    def test_listing_queries_do_not_grow_with_cow_count(self):
        with CaptureQueriesContext(connection) as initial:
            response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for position in range(5):
            Cow.objects.create(farm=self.farm, name=f"Cow {position}", identifier=f"B{position}")
        with CaptureQueriesContext(connection) as expanded:
            response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(initial), len(expanded))
        self.assertEqual(response.data["count"], 6)

    def test_missing_farm_returns_not_found(self):
        url = reverse("manage:cow_list_create", kwargs={"farm_id": uuid.uuid4()})
        self.assertEqual(self.client.get(url).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.client.post(url, self.payload, format="json").status_code, status.HTTP_404_NOT_FOUND)

    def test_missing_cow_returns_not_found(self):
        url = reverse("manage:cow_detail", kwargs={"farm_id": self.farm.pk, "cow_id": uuid.uuid4()})
        for method in ("get", "put", "patch", "delete"):
            with self.subTest(method=method):
                response = getattr(self.client, method)(url, data=self.payload if method in ("put", "patch") else None, format="json")
                self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
