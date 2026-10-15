from django.conf import settings
from django.test import SimpleTestCase
from django.utils.translation import override
from rest_framework import serializers


class InterfaceLanguageTests(SimpleTestCase):
    def test_default_validation_messages_are_in_portuguese(self):
        self.assertEqual(settings.LANGUAGE_CODE, "pt-br")
        with override(settings.LANGUAGE_CODE):
            serializer = serializers.Serializer()
            serializer.fields["name"] = serializers.CharField()
            serializer.initial_data = {}
            self.assertFalse(serializer.is_valid())
            self.assertEqual(str(serializer.errors["name"][0]), "Este campo é obrigatório.")
