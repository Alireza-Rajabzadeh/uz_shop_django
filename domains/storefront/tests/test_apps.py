from django.apps import apps
from django.test import SimpleTestCase

from domains.storefront.apps import StorefrontConfig


class StorefrontConfigTests(SimpleTestCase):
    def test_app_config(self):
        self.assertEqual(StorefrontConfig.name, "domains.storefront")
        self.assertEqual(apps.get_app_config("storefront").name, "domains.storefront")
