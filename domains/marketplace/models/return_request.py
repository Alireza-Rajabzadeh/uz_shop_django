from django.db import models


class MarketplaceReturnRequest(models.Model):
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
        db_table = "marketplace_return_request"
        indexes = [
            models.Index(
                fields=["customer", "-requested_at"],
                name="mkt_ret_customer_req_idx",
            ),
            models.Index(
                fields=["order", "status"],
                name="mkt_ret_order_status_idx",
            ),
        ]

    order = models.ForeignKey(
        "marketplace.MarketplaceOrder",
        on_delete=models.PROTECT,
        related_name="return_requests",
    )
    customer = models.ForeignKey(
        "customer.Customer",
        on_delete=models.PROTECT,
        related_name="marketplace_return_requests",
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
        return f"Marketplace return #{self.pk} for order #{self.order_id}"


class MarketplaceReturnRequestItem(models.Model):
    class Meta:
        db_table = "marketplace_return_request_item"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name="marketplace_return_item_quantity_gt_0",
            ),
            models.UniqueConstraint(
                fields=["return_request", "order_item"],
                name="marketplace_return_unique_order_item",
            ),
        ]
        indexes = [
            models.Index(
                fields=["order_item"],
                name="mkt_ret_item_order_item_idx",
            ),
        ]

    return_request = models.ForeignKey(
        MarketplaceReturnRequest,
        on_delete=models.CASCADE,
        related_name="items",
    )
    order_item = models.ForeignKey(
        "marketplace.MarketplaceOrderItem",
        on_delete=models.PROTECT,
        related_name="return_request_items",
    )
    quantity = models.PositiveIntegerField()
    reason = models.TextField(null=True, blank=True)

    def __str__(self):
        return f"Marketplace return item #{self.pk} for order item #{self.order_item_id}"


class MarketplaceReturnRequestEvidence(models.Model):
    class Meta:
        db_table = "marketplace_return_request_evidence"
        ordering = ["position", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["return_request", "position"],
                name="marketplace_return_unique_evidence_position",
            ),
        ]

    return_request = models.ForeignKey(
        MarketplaceReturnRequest,
        on_delete=models.CASCADE,
        related_name="evidence",
    )
    file = models.ForeignKey(
        "files.File",
        on_delete=models.PROTECT,
        related_name="marketplace_return_request_evidence",
    )
    position = models.PositiveSmallIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
