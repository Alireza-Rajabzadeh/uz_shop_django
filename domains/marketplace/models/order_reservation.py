from django.db import models


class MarketplaceOrderItemReservation(models.Model):
    """The stock one marketplace order line holds.

    This is an audit trail of what was taken, not the algorithm that takes it:
    reservation, release, consumption and restoration all live in
    ``InventoryService`` so the marketplace flow cannot grow its own copy.
    The shop table's generic ``inventory_type`` / ``inventory_id`` columns are
    deliberately absent; the linked rows are the whole record.
    """

    class Meta:
        db_table = "marketplace_order_item_reservation"
        indexes = [
            models.Index(
                fields=["linked_inventory"],
                name="mkt_ord_resrv_invtry_idx",
            ),
            models.Index(
                fields=["linked_unit"],
                name="mkt_ord_resrv_unit_idx",
            ),
        ]

    order_item = models.ForeignKey(
        "marketplace.MarketplaceOrderItem",
        on_delete=models.CASCADE,
        related_name="reservations",
    )
    quantity = models.PositiveIntegerField(default=1)
    linked_inventory = models.ForeignKey(
        "inventory.Inventory",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="marketplace_order_reservations",
    )
    linked_unit = models.ForeignKey(
        "inventory.InventoryUnit",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="marketplace_order_reservations",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"inventory#{self.linked_inventory_id} x{self.quantity}"
