from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from domains.notifications.models import Provider, ProviderStatus, SentNotification
from domains.notifications.services import NotificationError, ProviderService, SMSService


@override_settings(NOTIFICATIONS_ALLOW_FAKE_SMS=True)
class NotificationServiceTests(TestCase):
    def setUp(self):
        self.provider = Provider.objects.get(code="fake-sms")
        self.service = SMSService()

    def test_send_uses_default_provider_and_enqueues_after_commit(self):
        with patch.object(self.service, "_enqueue") as enqueue:
            with self.captureOnCommitCallbacks(execute=True):
                notification = self.service.send("+989121234567", "Test message")

        self.assertEqual(notification.provider, self.provider)
        self.assertEqual(notification.status, SentNotification.Status.PENDING)
        enqueue.assert_called_once_with(notification.pk, expires_at=None)

    @patch("domains.notifications.tasks.send_sms_notification.apply_async", side_effect=RuntimeError("broker down"))
    def test_broker_failure_marks_notification_failed(self, apply_async):
        with self.captureOnCommitCallbacks(execute=True):
            notification = self.service.send("+989121234567", "Test message")

        notification.refresh_from_db()
        self.assertEqual(notification.status, SentNotification.Status.FAILED)
        self.assertEqual(notification.error_message, "The SMS could not be queued.")

    @patch("domains.notifications.tasks.refresh_sms_delivery_status.apply_async")
    def test_process_marks_notification_sent(self, delivery_task):
        notification = SentNotification.objects.create(
            service_type=Provider.ServiceType.SMS,
            receiver="09121234567",
            message="Test message",
            is_sensitive=True,
            provider=self.provider,
            provider_code=self.provider.code,
            provider_name=self.provider.name,
        )

        notification = self.service.process(notification.pk)

        self.assertEqual(notification.status, SentNotification.Status.SENT)
        self.assertTrue(notification.external_id.startswith("fake-"))
        self.assertEqual(notification.message, "[redacted]")
        self.assertIsNotNone(notification.sent_at)
        delivery_task.assert_called_once()

    def test_refresh_delivery_status_marks_message_delivered(self):
        notification = SentNotification.objects.create(
            service_type=Provider.ServiceType.SMS,
            receiver="09121234567",
            message="Test message",
            provider=self.provider,
            provider_code=self.provider.code,
            provider_name=self.provider.name,
            status=SentNotification.Status.SENT,
            external_id="fake-message",
        )

        notification = self.service.refresh_delivery_status(notification.pk)

        self.assertEqual(notification.status, SentNotification.Status.DELIVERED)
        self.assertIsNotNone(notification.delivered_at)

    def test_expired_sensitive_notification_is_failed_and_redacted(self):
        from domains.notifications.tasks import expire_sensitive_notification

        notification = SentNotification.objects.create(
            service_type=Provider.ServiceType.SMS,
            receiver="09121234567",
            message="Secret code",
            is_sensitive=True,
            provider=self.provider,
            provider_code=self.provider.code,
            provider_name=self.provider.name,
        )

        expire_sensitive_notification(str(notification.pk))

        notification.refresh_from_db()
        self.assertEqual(notification.status, SentNotification.Status.FAILED)
        self.assertEqual(notification.message, "[redacted]")

    @patch("domains.notifications.providers.sms.factory.SMSProviderFactory.create")
    def test_worker_does_not_send_expired_notification(self, create_adapter):
        notification = SentNotification.objects.create(
            service_type=Provider.ServiceType.SMS,
            receiver="09121234567",
            message="Expired code",
            is_sensitive=True,
            expires_at=timezone.now() - timedelta(seconds=1),
            provider=self.provider,
            provider_code=self.provider.code,
            provider_name=self.provider.name,
        )

        notification = self.service.process(notification.pk)

        self.assertEqual(notification.status, SentNotification.Status.FAILED)
        self.assertEqual(notification.message, "[redacted]")
        create_adapter.assert_not_called()

    def test_health_and_balance_use_provider_adapter(self):
        self.assertTrue(self.service.provider_health().healthy)
        self.assertIsNone(self.service.provider_balance().amount)

    def test_send_rejects_invalid_receiver(self):
        with self.assertRaises(NotificationError) as caught:
            self.service.send("not-a-phone", "Test message")

        self.assertIn("receiver", caught.exception.errors)

    def test_unsupported_provider_failure_is_audited(self):
        self.provider.code = "unsupported"
        self.provider.save(update_fields=["code"])
        notification = SentNotification.objects.create(
            service_type=Provider.ServiceType.SMS,
            receiver="09121234567",
            message="Test message",
            provider=self.provider,
            provider_code=self.provider.code,
            provider_name=self.provider.name,
        )

        notification = self.service.process(notification.pk)

        self.assertEqual(notification.status, SentNotification.Status.FAILED)
        self.assertEqual(notification.error_message, "The SMS provider could not send this message.")


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

    @patch("domains.notifications.services.notification_service.SMSService._enqueue")
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
