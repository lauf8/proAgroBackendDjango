from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .models import User


class PasswordChangeFeatureTests(APITestCase):
    def setUp(self):
        self.current_password = "OriginalPassword123!"
        self.new_password = "UpdatedPassword456!"
        self.user = User.objects.create_user(
            "user@example.com", self.current_password, name="User",
        )
        self.other_user = User.objects.create_user(
            "other@example.com", self.current_password, name="Other",
        )
        self.url = reverse("accounts:change_password")
        response = self.login(self.user.email, self.current_password)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
        self.payload = {
            "current_password": self.current_password,
            "new_password": self.new_password,
        }

    def login(self, email, password):
        return self.client.post(
            reverse("accounts:login"), {"email": email, "password": password}, format="json",
        )

    def assert_password_unchanged(self):
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.current_password))

    def test_authenticated_user_changes_own_password(self):
        response = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(response.content, b"")
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.new_password))
        self.assertFalse(self.user.check_password(self.current_password))
        self.assertNotEqual(self.user.password, self.new_password)
        self.client.credentials()
        self.assertEqual(
            self.login(self.user.email, self.current_password).status_code,
            status.HTTP_401_UNAUTHORIZED,
        )
        self.assertEqual(
            self.login(self.user.email, self.new_password).status_code,
            status.HTTP_200_OK,
        )

    def test_unauthenticated_user_is_rejected(self):
        self.client.credentials()
        response = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assert_password_unchanged()

    def test_invalid_token_is_rejected(self):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer invalid-token")
        response = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assert_password_unchanged()

    def test_incorrect_current_password_is_rejected(self):
        self.payload["current_password"] = "IncorrectPassword123!"
        response = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("current_password", response.data)
        self.assert_password_unchanged()

    def test_new_password_uses_django_validators(self):
        for password in ("short", "password", "123456789012", self.user.email):
            with self.subTest(password=password):
                self.payload["new_password"] = password
                response = self.client.post(self.url, self.payload, format="json")
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn("new_password", response.data)
                self.assert_password_unchanged()

    def test_required_fields(self):
        for field in ("current_password", "new_password"):
            with self.subTest(field=field):
                payload = {key: value for key, value in self.payload.items() if key != field}
                response = self.client.post(self.url, payload, format="json")
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn(field, response.data)
                self.assert_password_unchanged()

    def test_blank_passwords_are_rejected(self):
        for field in ("current_password", "new_password"):
            with self.subTest(field=field):
                payload = {**self.payload, field: ""}
                response = self.client.post(self.url, payload, format="json")
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assert_password_unchanged()

    def test_cannot_target_other_users_or_modify_privileges(self):
        self.payload.update({
            "id": str(self.other_user.pk), "user_id": str(self.other_user.pk),
            "email": self.other_user.email, "is_superuser": True, "is_staff": True,
        })
        response = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.user.refresh_from_db()
        self.other_user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.new_password))
        self.assertTrue(self.other_user.check_password(self.current_password))
        self.assertEqual(self.user.email, "user@example.com")
        self.assertFalse(self.user.is_superuser)
        self.assertFalse(self.user.is_staff)

    def test_password_whitespace_is_preserved(self):
        self.payload["new_password"] = "  UpdatedPassword456!  "
        response = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("  UpdatedPassword456!  "))
        self.assertFalse(self.user.check_password("UpdatedPassword456!"))

    def test_only_post_is_supported(self):
        for method in ("get", "put", "patch", "delete"):
            with self.subTest(method=method):
                response = getattr(self.client, method)(self.url)
                self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assert_password_unchanged()
