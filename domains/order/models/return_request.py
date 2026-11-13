from django.db import models


class ReturnRequest(models.Model):
    class RefundDestinationType(models.TextChoices):
        CARD = "card", "Card"
        ACCOUNT = "account", "Account"

    class Status(models.TextChoices):
        REQUESTED = "requested", "Requested"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        RECEIVED = "received", "Received"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    class Meta:
        db_table = "shop_return_request"
        indexes = [
            models.Index(
                fields=["customer", "-requested_at"],
                name="shop_ret_customer_req_idx",
            ),
            models.Index(
                fields=["order", "status"],
                name="shop_ret_order_status_idx",
            ),
        ]

    order = models.ForeignKey(
        "order.Order",
        on_delete=models.PROTECT,
        related_name="return_requests",
    )
    customer = models.ForeignKey(
        "customer.Customer",
        on_delete=models.PROTECT,
        related_name="return_requests",
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.REQUESTED,
    )
    reason = models.TextField()
    customer_note = models.TextField(null=True, blank=True)
    refund_destination_type = models.CharField(
        max_length=16,
        choices=RefundDestinationType.choices,
    )
    refund_destination_value = models.CharField(max_length=64)
    admin_note = models.TextField(null=True, blank=True)
    customer_response = models.TextField(null=True, blank=True)
    requested_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    received_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Return request #{self.pk} for order #{self.order_id}"
