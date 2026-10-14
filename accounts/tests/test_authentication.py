from datetime import timedelta
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken
from accounts.models import User


class JWTAuthenticationFeatureTests(APITestCase):
    def setUp(self):
        self.password = "StrongPassword123!"
        self.user = User.objects.create_user(
            email="farmer@example.com", password=self.password, name="Farmer"
        )
        self.login_url = reverse("accounts:login")
        self.refresh_url = reverse("accounts:refresh")
        self.logout_url = reverse("accounts:logout")
        self.protected_url = reverse("accounts:current_user")

    def login(self, user=None):
        response = self.client.post(
            self.login_url,
            {"email": (user or self.user).email, "password": self.password},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response.data

    def test_login_with_email_and_password(self):
        tokens = self.login()
        self.assertEqual(set(tokens), {"access", "refresh"})
        access = AccessToken(tokens["access"])
        self.assertEqual(access["user_id"], str(self.user.pk))
        self.assertEqual(access["name"], self.user.name)
        self.assertEqual(access["email"], self.user.email)
        self.assertIs(access["is_superuser"], False)
        self.assertEqual(
            set(access.payload),
            {"token_type", "exp", "iat", "jti", "user_id", "name", "email", "is_superuser"},
        )
        self.assertEqual(access["exp"] - access["iat"], 15 * 60)
        refresh = RefreshToken(tokens["refresh"])
        self.assertEqual(refresh["exp"] - refresh["iat"], 7 * 24 * 60 * 60)

    def test_superuser_claim(self):
        admin = User.objects.create_superuser(
            "admin@example.com", self.password, name="Admin"
        )
        self.assertIs(AccessToken(self.login(admin)["access"])["is_superuser"], True)

    def test_login_rejects_invalid_credentials(self):
        for email, password in (
            (self.user.email, "wrong-password"),
            ("unknown@example.com", self.password),
        ):
            with self.subTest(email=email):
                response = self.client.post(
                    self.login_url, {"email": email, "password": password}, format="json"
                )
                self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_login_requires_email_and_password(self):
        for payload in ({}, {"email": self.user.email}, {"password": self.password}):
            with self.subTest(payload=payload):
                response = self.client.post(self.login_url, payload, format="json")
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_inactive_user_cannot_login(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        response = self.client.post(
            self.login_url,
            {"email": self.user.email, "password": self.password},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_refresh_rotates_and_blacklists_previous_token(self):
        tokens = self.login()
        old_refresh = RefreshToken(tokens["refresh"])
        response = self.client.post(
            self.refresh_url, {"refresh": tokens["refresh"]}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotEqual(response.data["refresh"], tokens["refresh"])
        self.assertTrue(BlacklistedToken.objects.filter(token__jti=old_refresh["jti"]).exists())
        access = AccessToken(response.data["access"])
        self.assertEqual(access["email"], self.user.email)
        self.assertEqual(access["name"], self.user.name)
        self.assertIs(access["is_superuser"], False)
        self.assertEqual(access["exp"] - access["iat"], 15 * 60)
        new_refresh = RefreshToken(response.data["refresh"])
        self.assertEqual(new_refresh["exp"] - new_refresh["iat"], 7 * 24 * 60 * 60)
        rejected = self.client.post(
            self.refresh_url, {"refresh": tokens["refresh"]}, format="json"
        )
        self.assertEqual(rejected.status_code, status.HTTP_401_UNAUTHORIZED)
        accepted = self.client.post(
            self.refresh_url, {"refresh": response.data["refresh"]}, format="json"
        )
        self.assertEqual(accepted.status_code, status.HTTP_200_OK)

    def test_logout_blacklists_refresh_without_access_token(self):
        tokens = self.login()
        refresh = RefreshToken(tokens["refresh"])
        response = self.client.post(
            self.logout_url, {"refresh": tokens["refresh"]}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(BlacklistedToken.objects.filter(token__jti=refresh["jti"]).exists())
        response = self.client.post(
            self.refresh_url, {"refresh": tokens["refresh"]}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_repeated_logout_rejects_blacklisted_token(self):
        tokens = self.login()
        self.client.post(self.logout_url, {"refresh": tokens["refresh"]}, format="json")
        response = self.client.post(
            self.logout_url, {"refresh": tokens["refresh"]}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_invalid_refresh_and_logout_tokens(self):
        access = self.login()["access"]
        for url in (self.refresh_url, self.logout_url):
            for token in ("invalid-token", access):
                with self.subTest(url=url, token=token):
                    response = self.client.post(url, {"refresh": token}, format="json")
                    self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_refresh_and_logout_require_refresh_field(self):
        for url in (self.refresh_url, self.logout_url):
            with self.subTest(url=url):
                response = self.client.post(url, {}, format="json")
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_protected_route_requires_authentication(self):
        response = self.client.get(self.protected_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_protected_route_accepts_access_token(self):
        tokens = self.login()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        response = self.client.get(self.protected_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {
            "id": str(self.user.pk),
            "name": self.user.name,
            "email": self.user.email,
            "is_superuser": False,
        })

    def test_protected_route_rejects_invalid_and_refresh_tokens(self):
        tokens = self.login()
        for token in ("invalid-token", tokens["refresh"]):
            with self.subTest(token=token):
                self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
                response = self.client.get(self.protected_url)
                self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_expired_access_token_is_rejected(self):
        access = AccessToken(self.login()["access"])
        access.set_exp(from_time=timezone.now() - timedelta(hours=1), lifetime=timedelta(minutes=15))
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        response = self.client.get(self.protected_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_inactive_user_cannot_access_protected_route(self):
        tokens = self.login()
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        response = self.client.get(self.protected_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_public_endpoints_ignore_invalid_authorization_header(self):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer invalid-token")
        tokens = self.login()
        response = self.client.post(
            self.refresh_url, {"refresh": tokens["refresh"]}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response = self.client.post(
            self.logout_url, {"refresh": response.data["refresh"]}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_logout_does_not_revoke_existing_access_token(self):
        tokens = self.login()
        self.client.post(self.logout_url, {"refresh": tokens["refresh"]}, format="json")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        response = self.client.get(self.protected_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
