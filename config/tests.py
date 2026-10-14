from importlib import import_module

from django.test import SimpleTestCase


class ApplicationStartupTests(SimpleTestCase):
    def test_wsgi_application_loads(self):
        application = import_module("config.wsgi").application
        self.assertTrue(callable(application))

    def test_asgi_application_loads(self):
        application = import_module("config.asgi").application
        self.assertTrue(callable(application))
