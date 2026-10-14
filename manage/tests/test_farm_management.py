import uuid

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import FarmMembership, User
from manage.models import Cow, Farm


class FarmManagementFeatureTests(APITestCase):
    def setUp(self):
        self.password = "StrongPassword123!"
        self.superuser = User.objects.create_superuser(
            "admin@example.com", self.password, name="Admin",
        )
        self.owner = User.objects.create_user(
            "owner@example.com", self.password, name="Owner",
        )
        self.farm = Farm.objects.create(name="Active farm", owner_name="Owner", state="BA")
        self.inactive_farm = Farm.objects.create(name="Inactive farm", is_active=False)
        self.membership = FarmMembership.objects.create(
            farm=self.farm, user=self.owner, role="owner", is_active=True,
        )
        self.list_url = reverse("manage:farm_create")
        self.update_url = reverse("manage:farm_update", kwargs={"farm_id": self.farm.pk})
        self.authenticate(self.superuser)

    def authenticate(self, user):
        response = self.client.post(
            reverse("accounts:login"),
            {"email": user.email, "password": self.password}, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")

    def test_list_includes_active_and_inactive_farms(self):
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 2)
        self.assertEqual([farm["name"] for farm in response.data["results"]], ["Active farm", "Inactive farm"])
        self.assertEqual(response.data["results"][0]["owner_email"], self.owner.email)
        self.assertIsNone(response.data["results"][1]["owner_email"])
        self.assertNotIn("password", response.content.decode())

    def test_empty_list(self):
        response = self.client.get(self.list_url, {"is_active": "true"})
        self.assertEqual(response.data["count"], 1)
        self.farm.is_active = False
        self.farm.save()
        response = self.client.get(self.list_url, {"is_active": "true"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 0)
        self.assertEqual(response.data["results"], [])

    def test_filter_active_and_inactive_farms(self):
        for is_active, farm in (("true", self.farm), ("false", self.inactive_farm)):
            with self.subTest(is_active=is_active):
                response = self.client.get(self.list_url, {"is_active": is_active})
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.assertEqual(response.data["count"], 1)
                self.assertEqual(response.data["results"][0]["id"], str(farm.pk))

    def test_invalid_active_filter_is_rejected(self):
        response = self.client.get(self.list_url, {"is_active": "invalid"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("is_active", response.data)

    def test_pagination(self):
        response = self.client.get(self.list_url, {"page_size": 1})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertIsNotNone(response.data["next"])
        second = self.client.get(self.list_url, {"page_size": 1, "page": 2})
        self.assertEqual(second.data["results"][0]["id"], str(self.inactive_farm.pk))

    def test_listing_query_count_does_not_grow_with_farms(self):
        with CaptureQueriesContext(connection) as initial:
            response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for position in range(5):
            farm = Farm.objects.create(name=f"Additional farm {position}")
            FarmMembership.objects.create(farm=farm, user=self.owner, role="owner")
        with CaptureQueriesContext(connection) as expanded:
            response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(initial), len(expanded))
        self.assertEqual(response.data["count"], 7)

    def test_partial_update(self):
        response = self.client.patch(self.update_url, {"city": "Cacule", "notes": "Updated"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.farm.refresh_from_db()
        self.assertEqual(self.farm.city, "Cacule")
        self.assertEqual(self.farm.notes, "Updated")
        self.assertEqual(self.farm.name, "Active farm")
        self.assertEqual(response.data["owner_email"], self.owner.email)

    def test_full_update(self):
        payload = {
            "name": "Updated farm", "owner_name": "Updated owner label",
            "city": "Cacule", "state": "BA", "phone": "77999999999",
            "notes": "Updated notes", "is_active": True,
        }
        response = self.client.put(self.update_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.farm.refresh_from_db()
        for field, value in payload.items():
            self.assertEqual(getattr(self.farm, field), value)

    def test_inactivation_preserves_farm_user_membership_and_history(self):
        cow = Cow.objects.create(farm=self.farm, name="Cow", identifier="A1")
        response = self.client.patch(self.update_url, {"is_active": False}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["is_active"])
        self.farm.refresh_from_db()
        self.owner.refresh_from_db()
        self.membership.refresh_from_db()
        self.assertFalse(self.farm.is_active)
        self.assertTrue(self.owner.is_active)
        self.assertTrue(self.membership.is_active)
        self.assertTrue(Cow.objects.filter(pk=cow.pk, farm=self.farm).exists())
        self.assertEqual(Farm.objects.count(), 2)

    def test_inactive_farm_can_be_edited_and_reactivated(self):
        url = reverse("manage:farm_update", kwargs={"farm_id": self.inactive_farm.pk})
        response = self.client.patch(url, {"name": "Reactivated farm", "is_active": True}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.inactive_farm.refresh_from_db()
        self.assertTrue(self.inactive_farm.is_active)
        self.assertEqual(self.inactive_farm.name, "Reactivated farm")

    def test_cannot_modify_owner_account_membership_or_audit(self):
        created_at = self.farm.created_at
        response = self.client.patch(self.update_url, {
            "id": str(uuid.uuid4()), "created_at": "2000-01-01T00:00:00Z",
            "updated_at": "2000-01-01T00:00:00Z", "owner_email": "changed@example.com",
            "admin": {"name": "Changed", "email": "changed@example.com", "password": "ChangedPassword123!"},
            "role": "admin", "is_superuser": True,
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.farm.refresh_from_db()
        self.owner.refresh_from_db()
        self.membership.refresh_from_db()
        self.assertEqual(self.farm.created_at, created_at)
        self.assertNotEqual(self.farm.updated_at.year, 2000)
        self.assertEqual(self.owner.email, "owner@example.com")
        self.assertTrue(self.owner.check_password(self.password))
        self.assertFalse(self.owner.is_superuser)
        self.assertEqual(self.membership.role, "owner")
        self.assertEqual(User.objects.count(), 2)

    def test_invalid_updates_do_not_change_farm(self):
        for payload in ({"name": ""}, {"state": "INVALID"}, {"is_active": "invalid"}):
            with self.subTest(payload=payload):
                response = self.client.patch(self.update_url, payload, format="json")
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.farm.refresh_from_db()
                self.assertEqual(self.farm.name, "Active farm")
                self.assertEqual(self.farm.state, "BA")
                self.assertTrue(self.farm.is_active)

    def test_full_update_requires_name(self):
        response = self.client.put(self.update_url, {"city": "Cacule"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("name", response.data)

    def test_nonexistent_farm_returns_not_found(self):
        url = reverse("manage:farm_update", kwargs={"farm_id": uuid.uuid4()})
        response = self.client.patch(url, {"name": "Updated"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_regular_and_staff_users_cannot_list_or_edit_unrelated_farm(self):
        for is_staff in (False, True):
            with self.subTest(is_staff=is_staff):
                self.owner.is_staff = is_staff
                self.owner.save(update_fields=["is_staff"])
                self.authenticate(self.owner)
                self.assertEqual(self.client.get(self.list_url).status_code, status.HTTP_403_FORBIDDEN)
                unrelated_url = reverse("manage:farm_update", kwargs={"farm_id": self.inactive_farm.pk})
                response = self.client.patch(unrelated_url, {"name": "Unauthorized"}, format="json")
                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.inactive_farm.refresh_from_db()
        self.assertEqual(self.inactive_farm.name, "Inactive farm")

    def test_unauthenticated_requests_are_rejected(self):
        self.client.credentials()
        self.assertEqual(self.client.get(self.list_url).status_code, status.HTTP_401_UNAUTHORIZED)
        response = self.client.patch(self.update_url, {"is_active": False}, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_invalid_token_is_rejected(self):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer invalid-token")
        self.assertEqual(self.client.get(self.list_url).status_code, status.HTTP_401_UNAUTHORIZED)
        response = self.client.patch(self.update_url, {"is_active": False}, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_delete_is_not_available(self):
        for url in (self.list_url, self.update_url):
            with self.subTest(url=url):
                response = self.client.delete(url)
                self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertTrue(Farm.objects.filter(pk=self.farm.pk).exists())


    def test_active_farm_member_can_patch_and_put_for_every_role(self):
        self.authenticate(self.owner)
        for role in FarmMembership.Role.values:
            self.membership.role = role
            self.membership.save(update_fields=["role"])
            for method in ("patch", "put"):
                with self.subTest(role=role, method=method):
                    name = f"Updated by {role} using {method}"
                    response = getattr(self.client, method)(
                        self.update_url, {"name": name}, format="json",
                    )
                    self.assertEqual(response.status_code, status.HTTP_200_OK)
                    self.farm.refresh_from_db()
                    self.assertEqual(self.farm.name, name)

    def test_inactive_membership_cannot_edit_farm(self):
        self.authenticate(self.owner)
        self.membership.is_active = False
        self.membership.save(update_fields=["is_active"])
        for method in ("patch", "put"):
            with self.subTest(method=method):
                response = getattr(self.client, method)(
                    self.update_url, {"name": "Unauthorized"}, format="json",
                )
                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.farm.refresh_from_db()
        self.assertEqual(self.farm.name, "Active farm")

    def test_user_without_membership_cannot_edit_farm(self):
        self.superuser.is_superuser = False
        self.superuser.save(update_fields=["is_superuser"])
        response = self.client.patch(self.update_url, {"name": "Unauthorized"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.farm.refresh_from_db()
        self.assertEqual(self.farm.name, "Active farm")

    def test_member_cannot_bypass_farm_permission_using_payload(self):
        self.authenticate(self.owner)
        url = reverse("manage:farm_update", kwargs={"farm_id": self.inactive_farm.pk})
        for method in ("patch", "put"):
            with self.subTest(method=method):
                response = getattr(self.client, method)(url, {
                    "id": str(self.farm.pk), "farm_id": str(self.farm.pk),
                    "name": "Unauthorized", "user_id": str(self.superuser.pk),
                    "is_superuser": True,
                }, format="json")
                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.inactive_farm.refresh_from_db()
        self.assertEqual(self.inactive_farm.name, "Inactive farm")

    def test_member_cannot_inactivate_or_reactivate_own_farm(self):
        self.authenticate(self.owner)
        for role in FarmMembership.Role.values:
            self.membership.role = role
            self.membership.save(update_fields=["role"])
            for current_status in (True, False):
                self.farm.is_active = current_status
                self.farm.save(update_fields=["is_active"])
                for method in ("patch", "put"):
                    with self.subTest(role=role, current_status=current_status, method=method):
                        response = getattr(self.client, method)(self.update_url, {
                            "name": "Unauthorized change", "is_active": not current_status,
                        }, format="json")
                        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
                        self.assertIn("is_active", response.data)
                        self.farm.refresh_from_db()
                        self.assertEqual(self.farm.is_active, current_status)
                        self.assertEqual(self.farm.name, "Active farm")
        self.membership.refresh_from_db()
        self.assertTrue(self.membership.is_active)

    def test_staff_member_cannot_change_farm_status(self):
        self.owner.is_staff = True
        self.owner.save(update_fields=["is_staff"])
        self.authenticate(self.owner)
        response = self.client.patch(self.update_url, {"is_active": False}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.farm.refresh_from_db()
        self.assertTrue(self.farm.is_active)

    def test_member_can_edit_other_fields_with_unchanged_status(self):
        self.authenticate(self.owner)
        for current_status in (True, False):
            self.farm.is_active = current_status
            self.farm.save(update_fields=["is_active"])
            for method in ("patch", "put"):
                with self.subTest(current_status=current_status, method=method):
                    response = getattr(self.client, method)(self.update_url, {
                        "name": "Updated farm", "is_active": current_status,
                    }, format="json")
                    self.assertEqual(response.status_code, status.HTTP_200_OK)
                    self.farm.refresh_from_db()
                    self.assertEqual(self.farm.name, "Updated farm")
                    self.assertEqual(self.farm.is_active, current_status)

    def test_member_cannot_delete_own_farm(self):
        self.authenticate(self.owner)
        response = self.client.delete(self.update_url)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertTrue(Farm.objects.filter(pk=self.farm.pk).exists())
