import uuid

from django.conf import settings
from django.db import models

from .provider import Provider


class SentNotification(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SENT = "sent", "Sent"
        DELIVERED = "delivered", "Delivered"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    service_type = models.CharField(max_length=20, choices=Provider.ServiceType.choices)
    receiver = models.CharField(max_length=320)
    message = models.TextField()
    is_sensitive = models.BooleanField(default=False)
    provider = models.ForeignKey(
        Provider,
        on_delete=models.PROTECT,
        related_name="sent_notifications",
    )
    provider_code = models.CharField(max_length=50)
    provider_name = models.CharField(max_length=100)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    external_id = models.CharField(max_length=255, blank=True)
    error_message = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sent_notifications",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "notifications_sent_notification"
        ordering = ["-created_at"]
        permissions = [("send_sms", "Can send SMS notifications")]
        indexes = [
            models.Index(
                fields=["status", "created_at"],
                name="notif_status_created_idx",
            ),
            models.Index(
                fields=["provider", "created_at"],
                name="notif_provider_created_idx",
            ),
            models.Index(fields=["receiver"], name="notifications_receiver_idx"),
        ]

    def __str__(self):
        return f"{self.get_service_type_display()} to {self.receiver}"
