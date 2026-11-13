from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from domains.notifications.models import Provider, ProviderStatus, SentNotification
from domains.notifications.services import NotificationError, ProviderService, SMSService



class ProviderServiceTests(TestCase):
    def setUp(self):
        self.active = ProviderStatus.objects.get(code="active")
        self.inactive = ProviderStatus.objects.get(code="inactive")
        self.provider = Provider.objects.get(code="fake-sms")

    def test_setting_new_default_unsets_existing_default(self):
        second = Provider.objects.create(
            name="Second SMS",
            code="second-sms",
            service_type=Provider.ServiceType.SMS,
            status=self.active,
        )

        ProviderService().update(second, is_default=True)

        self.provider.refresh_from_db()
        self.assertFalse(self.provider.is_default)
        self.assertTrue(second.is_default)

    def test_inactive_provider_cannot_be_default(self):
        with self.assertRaises(NotificationError) as caught:
            ProviderService().update(self.provider, status=self.inactive)

        self.assertIn("is_default", caught.exception.errors)

