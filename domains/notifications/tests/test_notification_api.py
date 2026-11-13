from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from domains.notifications.models import Provider, ProviderStatus, SentNotification
from domains.notifications.services import NotificationError, ProviderService, SMSService



@override_settings(NOTIFICATIONS_ALLOW_FAKE_SMS=True)
class NotificationAPITests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="notification-admin",
            password="password",
        )
        self.client.force_authenticate(self.user)
        self.provider = Provider.objects.get(code="fake-sms")

    def test_provider_list_filter_and_update(self):
        listing = self.client.get("/api/notifications/providers", {"service_type": "sms"})
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.data["data"]["count"], 1)

        update = self.client.patch(
            f"/api/notifications/providers/{self.provider.pk}",
            {"name": "Development SMS"},
            format="json",
        )
        self.assertEqual(update.status_code, 200)
        self.assertEqual(update.data["data"]["name"], "Development SMS")

        immutable = self.client.patch(
            f"/api/notifications/providers/{self.provider.pk}",
            {"code": "changed"},
            format="json",
        )
        self.assertEqual(immutable.status_code, 400)

    @patch("domains.notifications.services.sms_service.SMSService._enqueue")
    def test_manual_send_and_sent_list(self, enqueue):
        response = self.client.post(
            "/api/notifications/sms/send",
            {"receiver": "09121234567", "message": "Manual test"},
            format="json",
        )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data["data"]["status"], "pending")

        listing = self.client.get(
            "/api/notifications/sent",
            {"receiver": "0912", "status": "pending"},
        )
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.data["data"]["count"], 1)

    def test_non_admin_cannot_access_notification_api(self):
        user = get_user_model().objects.create_user(
            username="ordinary-user",
            password="password",
        )
        self.client.force_authenticate(user)

        response = self.client.get("/api/notifications/providers")

        self.assertEqual(response.status_code, 403)

