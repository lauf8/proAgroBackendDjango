import uuid
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone
from manage.models import Farm
from .models import FarmMembership, User


class AccountTests(TestCase):
    def test_create_user_with_normalized_email_and_password(self):
        user = User.objects.create_user("person@EXAMPLE.COM", "secret", name="Person")
        self.assertEqual(user.email, "person@example.com")
        self.assertTrue(user.check_password("secret"))
        self.assertIsInstance(user.pk, uuid.UUID)
        self.assertTrue(timezone.is_aware(user.created_at))
        self.assertFalse(hasattr(user, "username"))
        self.assertEqual(str(user), user.email)

    def test_direct_save_normalizes_email(self):
        user = User.objects.create(email="person@EXAMPLE.COM", name="Person")
        self.assertEqual(user.email, "person@example.com")

    def test_create_superuser(self):
        user = User.objects.create_superuser("admin@example.com", "secret", name="Admin")
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)

    def test_invalid_superuser_flags(self):
        for flag in ("is_staff", "is_superuser"):
            with self.subTest(flag=flag), self.assertRaises(ValueError):
                User.objects.create_superuser("admin@example.com", **{flag: False})

    def test_missing_email(self):
        with self.assertRaises(ValueError):
            User.objects.create_user("")

    def test_email_unique(self):
        User.objects.create_user("person@example.com")
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user("person@EXAMPLE.COM")

    def test_unique_membership(self):
        user = User.objects.create_user("person@example.com")
        farm = Farm.objects.create(name="Farm")
        FarmMembership.objects.create(user=user, farm=farm, role=FarmMembership.Role.OWNER)
        with self.assertRaises(IntegrityError), transaction.atomic():
            FarmMembership.objects.create(user=user, farm=farm, role=FarmMembership.Role.VIEWER)
