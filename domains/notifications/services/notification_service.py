import logging
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from core.utils import PhoneNormalizationError, normalize_phone
from domains.notifications.models import Provider, SentNotification
from domains.notifications.providers.sms import SMSProviderFactory

logger = logging.getLogger(__name__)
TEHRAN = ZoneInfo("Asia/Tehran")


class NotificationError(Exception):
    def __init__(self, errors):
        self.errors = errors
        super().__init__(str(errors))


class NotificationInProgress(Exception):
    pass


class ProviderService:
    ordering_fields = {
        "id": "id",
        "name": "name",
        "service_type": "service_type",
        "status_name": "status__name",
        "is_default": "is_default",
        "created_at": "created_at",
    }

    def list(self, name=None, service_type=None, status_id=None, is_default=None, ordering=None):
        queryset = Provider.objects.select_related("status")
        if name:
            queryset = queryset.filter(name__icontains=name.strip())
        if service_type:
            queryset = queryset.filter(service_type=service_type)
        if status_id is not None:
            queryset = queryset.filter(status_id=status_id)
        if is_default is not None:
            queryset = queryset.filter(is_default=is_default)
        direction = "-" if ordering and ordering.startswith("-") else ""
        requested = ordering.lstrip("-") if ordering else "id"
        return queryset.order_by(f"{direction}{self.ordering_fields[requested]}", "id")

    @staticmethod
    def get(provider_id):
        return Provider.objects.select_related("status").get(pk=provider_id)

    def update(self, provider, **data):
        name = data.get("name", provider.name).strip()
        status = data.get("status", provider.status)
        is_default = data.get("is_default", provider.is_default)
        if not name:
            raise NotificationError({"name": ["This field may not be blank."]})
        if is_default and status.code != "active":
            raise NotificationError({"is_default": ["The default provider must be active."]})

        try:
            with transaction.atomic():
                if is_default:
                    Provider.objects.filter(
                        service_type=provider.service_type,
                        is_default=True,
                    ).exclude(pk=provider.pk).update(is_default=False)
                provider.name = name
                provider.status = status
                provider.is_default = is_default
                provider.save(update_fields=["name", "status", "is_default", "updated_at"])
        except IntegrityError as exc:
            raise NotificationError(
                {"is_default": ["This service type already has a default provider."]}
            ) from exc
        return self.get(provider.pk)


class NotificationService:
    ordering_fields = {
        "created_at": "created_at",
        "updated_at": "updated_at",
        "receiver": "receiver",
        "service_type": "service_type",
        "provider_name": "provider_name",
        "status": "status",
    }

    def list(
        self,
        receiver=None,
        provider_id=None,
        service_type=None,
        status=None,
        created_from=None,
        created_to=None,
        ordering=None,
    ):
        queryset = SentNotification.objects.select_related("provider", "created_by")
        if receiver:
            queryset = queryset.filter(receiver__icontains=receiver.strip())
        if provider_id is not None:
            queryset = queryset.filter(provider_id=provider_id)
        if service_type:
            queryset = queryset.filter(service_type=service_type)
        if status:
            queryset = queryset.filter(status=status)
        if created_from:
            start = datetime.combine(created_from, time.min, tzinfo=TEHRAN)
            queryset = queryset.filter(created_at__gte=start)
        if created_to:
            end = datetime.combine(created_to + timedelta(days=1), time.min, tzinfo=TEHRAN)
            queryset = queryset.filter(created_at__lt=end)
        direction = "-" if ordering and ordering.startswith("-") else ""
        requested = ordering.lstrip("-") if ordering else "created_at"
        return queryset.order_by(f"{direction}{self.ordering_fields[requested]}", "-id")

    @staticmethod
    def get(notification_id):
        return SentNotification.objects.select_related("provider", "created_by").get(
            pk=notification_id
        )


class SMSService:
    @staticmethod
    def _active_provider(provider_id=None):
        queryset = Provider.objects.select_related("status").filter(
            service_type=Provider.ServiceType.SMS,
            status__code="active",
        )
        if provider_id is not None:
            provider = queryset.filter(pk=provider_id).first()
            if provider is None:
                raise NotificationError(
                    {"provider_id": ["Select an active SMS provider."]}
                )
            return provider
        provider = queryset.filter(is_default=True).first()
        if provider is None:
            raise NotificationError(
                {"provider_id": ["No active default SMS provider is configured."]}
            )
        return provider

    def send(
        self,
        receiver,
        message,
        provider_id=None,
        created_by=None,
        sensitive=False,
        expires_at=None,
    ):
        try:
            receiver = normalize_phone(receiver)
        except PhoneNormalizationError as exc:
            raise NotificationError(
                {"receiver": ["Enter a valid international or local mobile number."]}
            ) from exc
        message = message.strip()
        if not message:
            raise NotificationError({"message": ["This field may not be blank."]})
        if len(message) > 2000:
            raise NotificationError({"message": ["Message cannot exceed 2000 characters."]})

        provider = self._active_provider(provider_id)
        with transaction.atomic():
            notification = SentNotification.objects.create(
                service_type=Provider.ServiceType.SMS,
                receiver=receiver,
                message=message,
                is_sensitive=sensitive,
                provider=provider,
                provider_code=provider.code,
                provider_name=provider.name,
                created_by=created_by,
                expires_at=expires_at,
            )
            transaction.on_commit(
                lambda: self._enqueue(notification.pk, expires_at=expires_at)
            )
        return NotificationService.get(notification.pk)

    @staticmethod
    def _enqueue(notification_id, expires_at=None):
        from domains.notifications.tasks import (
            expire_sensitive_notification,
            send_sms_notification,
        )

        try:
            send_sms_notification.apply_async(args=[str(notification_id)])
        except Exception:
            logger.exception("Could not publish SMS notification %s", notification_id)
            SentNotification.objects.filter(
                pk=notification_id,
                status=SentNotification.Status.PENDING,
            ).update(
                status=SentNotification.Status.FAILED,
                error_message="The SMS could not be queued.",
            )
            SentNotification.objects.filter(pk=notification_id, is_sensitive=True).update(
                message="[redacted]"
            )
            return

        if expires_at is not None:
            try:
                countdown = max((expires_at - timezone.now()).total_seconds(), 0) + 5
                expire_sensitive_notification.apply_async(
                    args=[str(notification_id)],
                    countdown=countdown,
                )
            except Exception:
                logger.exception(
                    "Could not queue sensitive-message cleanup for notification %s",
                    notification_id,
                )

    def process(self, notification_id):
        stale_before = timezone.now() - timedelta(minutes=5)
        claimed = SentNotification.objects.filter(
            pk=notification_id,
            status=SentNotification.Status.PENDING,
        ).filter(
            Q(started_at__isnull=True) | Q(started_at__lt=stale_before)
        ).update(started_at=timezone.now())
        if not claimed:
            notification = NotificationService.get(notification_id)
            if notification.status == SentNotification.Status.PENDING:
                raise NotificationInProgress("This SMS is already being processed.")
            return notification

        notification = NotificationService.get(notification_id)
        if notification.expires_at and notification.expires_at <= timezone.now():
            SentNotification.objects.filter(pk=notification.pk).update(
                status=SentNotification.Status.FAILED,
                message="[redacted]" if notification.is_sensitive else notification.message,
                error_message="The notification expired before it could be sent.",
            )
            return NotificationService.get(notification.pk)
        try:
            adapter = SMSProviderFactory.create(notification.provider)
            result = adapter.send(notification.receiver, notification.message)
        except Exception:
            logger.exception("SMS provider failed for notification %s", notification.pk)
            SentNotification.objects.filter(pk=notification.pk).update(
                status=SentNotification.Status.FAILED,
                error_message="The SMS provider could not send this message.",
            )
            if notification.is_sensitive:
                SentNotification.objects.filter(pk=notification.pk).update(
                    message="[redacted]"
                )
        else:
            SentNotification.objects.filter(pk=notification.pk).update(
                status=SentNotification.Status.SENT,
                external_id=result.external_id,
                error_message="",
                sent_at=timezone.now(),
            )
            if notification.is_sensitive:
                SentNotification.objects.filter(pk=notification.pk).update(
                    message="[redacted]"
                )
            from domains.notifications.tasks import refresh_sms_delivery_status

            try:
                refresh_sms_delivery_status.apply_async(args=[str(notification.pk)], countdown=5)
            except Exception:
                logger.exception(
                    "Could not queue delivery check for notification %s", notification.pk
                )
        return NotificationService.get(notification.pk)

    def refresh_delivery_status(self, notification_id):
        notification = NotificationService.get(notification_id)
        if notification.service_type != Provider.ServiceType.SMS or not notification.external_id:
            raise NotificationError({"status": ["Delivery status is not available."]})
        adapter = SMSProviderFactory.create(notification.provider)
        result = adapter.get_delivery_status(notification.external_id)
        if result.status == SentNotification.Status.DELIVERED:
            SentNotification.objects.filter(pk=notification.pk).update(
                status=SentNotification.Status.DELIVERED,
                delivered_at=timezone.now(),
            )
        elif result.status == SentNotification.Status.FAILED:
            SentNotification.objects.filter(pk=notification.pk).update(
                status=SentNotification.Status.FAILED,
                error_message="The SMS provider reported a delivery failure.",
            )
        return NotificationService.get(notification.pk)

    def provider_health(self, provider_id=None):
        provider = self._active_provider(provider_id)
        return SMSProviderFactory.create(provider).get_health()

    def provider_balance(self, provider_id=None):
        provider = self._active_provider(provider_id)
        return SMSProviderFactory.create(provider).get_balance()
