from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from domains.notifications.models import SentNotification

TEHRAN = ZoneInfo("Asia/Tehran")


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
