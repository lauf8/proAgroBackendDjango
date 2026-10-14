from copy import deepcopy
from unittest.mock import patch

from django.db import IntegrityError
from django.urls import reverse
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.test import APITestCase

from accounts.models import FarmMembership, User
from manage.serializers.farm_serializers import FarmCreateSerializer, FarmDetailSerializer
from manage.models import Farm
from manage.services.farm_service import create_farm_with_owner


class FarmCreationFeatureTests(APITestCase):
    def setUp(self):
        self.password = "StrongPassword123!"
        self.superuser = User.objects.create_superuser(
            "superuser@example.com", self.password, name="Superuser",
        )
        self.regular_user = User.objects.create_user(
            "regular@example.com", self.password, name="Regular user",
        )
        self.url = reverse("manage:farm_create")
        self.payload = {
            "name": "Boa Vista Farm",
            "owner_name": "John Silva",
            "city": "Cacule",
            "state": "BA",
            "phone": "77999999999",
            "notes": "",
            "admin": {
                "name": "John Silva",
                "email": "john@example.com",
                "password": self.password,
            },
        }
        self.authenticate(self.superuser)

    def authenticate(self, user):
        response = self.client.post(
            reverse("accounts:login"),
            {"email": user.email, "password": self.password},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")

    def assert_no_creation(self, user_count=2):
        self.assertEqual(Farm.objects.count(), 0)
        self.assertEqual(FarmMembership.objects.count(), 0)
        self.assertEqual(User.objects.count(), user_count)

    def test_superuser_creates_farm_owner_and_membership(self):
        response = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Farm.objects.count(), 1)
        self.assertEqual(User.objects.count(), 3)
        farm = Farm.objects.get(pk=response.data["id"])
        self.assertEqual(farm.name, self.payload["name"])
        self.assertEqual(farm.owner_name, self.payload["owner_name"])
        self.assertTrue(farm.is_active)
        owner = User.objects.get(email=self.payload["admin"]["email"])
        self.assertFalse(owner.is_superuser)
        self.assertFalse(owner.is_staff)
        self.assertNotEqual(owner.password, self.password)
        self.assertTrue(owner.check_password(self.password))
        membership = FarmMembership.objects.get(farm=farm, user=owner)
        self.assertEqual(membership.role, FarmMembership.Role.OWNER)
        self.assertTrue(membership.is_active)
        self.assertEqual(response.data["owner_email"], owner.email)
        self.assertEqual(set(response.data), {
            "id", "name", "owner_name", "owner_email", "city", "state", "phone",
            "notes", "is_active", "created_at", "updated_at",
        })
        self.assertNotIn(self.password, response.content.decode())
        self.assertNotIn("password", response.content.decode())
        self.assertNotIn("admin", response.data)

    def test_created_owner_can_login(self):
        response = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.client.credentials()
        response = self.client.post(
            reverse("accounts:login"),
            {"email": self.payload["admin"]["email"], "password": self.password},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)

    def test_regular_user_is_forbidden(self):
        self.authenticate(self.regular_user)
        response = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assert_no_creation()

    def test_staff_user_is_forbidden(self):
        self.regular_user.is_staff = True
        self.regular_user.save(update_fields=["is_staff"])
        self.authenticate(self.regular_user)
        response = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assert_no_creation()

    def test_unauthenticated_user_is_rejected(self):
        self.client.credentials()
        response = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assert_no_creation()

    def test_permission_reads_database_user_instead_of_stale_claim(self):
        self.superuser.is_superuser = False
        self.superuser.save(update_fields=["is_superuser"])
        response = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assert_no_creation()

    def test_invalid_token_is_rejected(self):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer invalid-token")
        response = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assert_no_creation()

    def test_duplicate_email_is_rejected_case_insensitively(self):
        for email in ("regular@example.com", "REGULAR@EXAMPLE.COM", "Regular@Example.Com"):
            with self.subTest(email=email):
                payload = deepcopy(self.payload)
                payload["admin"]["email"] = email
                response = self.client.post(self.url, payload, format="json")
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn("email", response.data["admin"])
                self.assert_no_creation()

    def test_email_is_normalized(self):
        self.payload["admin"]["email"] = "John@EXAMPLE.COM"
        response = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["owner_email"], "john@example.com")
        self.assertTrue(User.objects.filter(email="john@example.com").exists())

    def test_invalid_passwords_are_rejected(self):
        for password in ("short", "password", "123456789012", "john@example.com"):
            with self.subTest(password=password):
                payload = deepcopy(self.payload)
                payload["admin"]["password"] = password
                response = self.client.post(self.url, payload, format="json")
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn("password", response.data["admin"])
                self.assert_no_creation()

    def test_privilege_and_membership_fields_cannot_be_controlled(self):
        self.payload["admin"].update({
            "is_superuser": True, "is_staff": True, "permissions": ["all"],
            "groups": ["admin"], "user_permissions": ["all"], "is_active": False,
        })
        self.payload.update({"role": "admin", "is_superuser": True, "is_staff": True})
        response = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        owner = User.objects.get(email="john@example.com")
        self.assertFalse(owner.is_superuser)
        self.assertFalse(owner.is_staff)
        self.assertTrue(owner.is_active)
        self.assertFalse(owner.groups.exists())
        self.assertFalse(owner.user_permissions.exists())
        membership = FarmMembership.objects.get(user=owner)
        self.assertEqual(membership.role, FarmMembership.Role.OWNER)
        self.assertTrue(membership.is_active)

    def test_audit_and_active_fields_cannot_be_controlled(self):
        self.payload.update({
            "id": "00000000-0000-0000-0000-000000000001",
            "is_active": False,
            "created_at": "2000-01-01T00:00:00Z",
            "updated_at": "2000-01-01T00:00:00Z",
        })
        response = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["is_active"])
        self.assertNotEqual(response.data["id"], self.payload["id"])
        self.assertNotEqual(response.data["created_at"], self.payload["created_at"])
        self.assertNotEqual(response.data["updated_at"], self.payload["updated_at"])

    def test_membership_failure_rolls_back_owner_and_farm(self):
        with patch(
            "manage.services.farm_service.FarmMembership.objects.create",
            side_effect=IntegrityError("Membership creation failed."),
        ), self.assertRaises(IntegrityError):
            self.client.post(self.url, self.payload, format="json")
        self.assert_no_creation()

    def test_farm_failure_rolls_back_owner(self):
        with patch(
            "manage.services.farm_service.Farm.objects.create",
            side_effect=IntegrityError("Farm creation failed."),
        ), self.assertRaises(IntegrityError):
            self.client.post(self.url, self.payload, format="json")
        self.assert_no_creation()

    def test_user_failure_creates_no_farm(self):
        with patch(
            "accounts.managers.UserManager.create_user",
            side_effect=IntegrityError("User creation failed."),
        ), self.assertRaises(IntegrityError):
            self.client.post(self.url, self.payload, format="json")
        self.assert_no_creation()

    def test_required_fields(self):
        for field in ("name", "admin", "admin.name", "admin.email", "admin.password"):
            with self.subTest(field=field):
                payload = deepcopy(self.payload)
                if field.startswith("admin."):
                    del payload["admin"][field.split(".")[1]]
                else:
                    del payload[field]
                response = self.client.post(self.url, payload, format="json")
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assert_no_creation()

    def test_invalid_farm_field(self):
        self.payload["state"] = "Invalid state"
        response = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("state", response.data)
        self.assert_no_creation()

    def test_collection_does_not_support_update_or_delete(self):
        for method in ("put", "patch", "delete"):
            with self.subTest(method=method):
                response = getattr(self.client, method)(self.url)
                self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assert_no_creation()

    def test_database_rejects_case_insensitive_duplicate_after_validation(self):
        serializer = FarmCreateSerializer(data=self.payload)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        User.objects.create_user("JOHN@example.com", self.password, name="Existing")
        with self.assertRaises(ValidationError) as error:
            serializer.save()
        self.assertIn("email", error.exception.detail["admin"])
        self.assert_no_creation(user_count=3)

    def test_duplicate_insert_after_validation_returns_http_400(self):
        def competing_creation(farm_data, owner_data):
            User.objects.create_user("JOHN@example.com", self.password, name="Existing")
            return create_farm_with_owner(farm_data, owner_data)

        with patch(
            "manage.serializers.farm_serializers.create_farm_with_owner", side_effect=competing_creation,
        ):
            response = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.data["admin"])
        self.assert_no_creation(user_count=3)

    def test_detail_uses_preloaded_active_owner_without_queries(self):
        farm = create_farm_with_owner(
            {key: value for key, value in self.payload.items() if key != "admin"},
            self.payload["admin"],
        )
        membership = farm.memberships.select_related("user").get()
        farm.active_owner_memberships = [membership]
        with self.assertNumQueries(0):
            data = FarmDetailSerializer(farm).data
        self.assertEqual(data["owner_email"], "john@example.com")

    def test_detail_ignores_inactive_owner_and_other_roles(self):
        farm = Farm.objects.create(name="Existing farm")
        FarmMembership.objects.create(
            farm=farm, user=self.regular_user, role="owner", is_active=False,
        )
        FarmMembership.objects.create(
            farm=farm, user=self.superuser, role="admin", is_active=True,
        )
        self.assertIsNone(FarmDetailSerializer(farm).data["owner_email"])
