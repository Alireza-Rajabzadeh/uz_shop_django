from django.test import SimpleTestCase
from kombu.transport.redis import GlobalKeyPrefixMixin

from config.celery import app  # noqa: F401


class CeleryRedisNamespaceTests(SimpleTestCase):
    def test_exists_uses_global_key_prefix(self):
        prefixer = object.__new__(GlobalKeyPrefixMixin)
        prefixer.global_keyprefix = "backend:"

        self.assertEqual(
            prefixer._prefix_args(("EXISTS", "celery")),
            ["EXISTS", "backend:celery"],
        )
