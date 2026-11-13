from django.db import models
from django.db.models import Q

from .provider_status import ProviderStatus


class Provider(models.Model):
    class ServiceType(models.TextChoices):
        SMS = "sms", "SMS"
        EMAIL = "email", "Email"
        PUSH = "push", "Push notification"

    name = models.CharField(max_length=100)
    code = models.SlugField(max_length=50, unique=True)
    service_type = models.CharField(max_length=20, choices=ServiceType.choices)
    status = models.ForeignKey(
        ProviderStatus,
        on_delete=models.PROTECT,
        related_name="providers",
    )
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "notifications_provider"
        ordering = ["service_type", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["service_type"],
                condition=Q(is_default=True),
                name="notifications_one_default_per_type",
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.get_service_type_display()})"
