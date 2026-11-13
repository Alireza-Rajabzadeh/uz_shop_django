from django.db import IntegrityError, transaction

from domains.notifications.models import Provider
from .exceptions import NotificationError


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
