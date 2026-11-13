from django.db import models


class PackagePriceHistory(models.Model):
    """Append-only audit of a package's price and discount.

    Written by `domains.packages.signals`, not by any one view or service,
    so every write path that reaches `Package.save()` leaves the same trail.
    Only the new values are stored: the previous row is the "before".

    `package` is PROTECT so deleting a package can never take its pricing
    audit with it — the same policy as `OfferPriceHistory`.
    """

    package = models.ForeignKey(
        "packages.Package",
        on_delete=models.PROTECT,
        related_name="price_history",
    )
    price = models.DecimalField(max_digits=15, decimal_places=2)
    off_discount = models.DecimalField(max_digits=5, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "packages_package_price_history"
        # Chronological: readers get oldest first, so the newest row is the
        # current pricing and the rows below it are the path taken here.
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(
                fields=["package", "created_at"],
                name="pph_package_created_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(price__gte=0),
                name="packages_price_history_price_gte_zero",
            ),
            models.CheckConstraint(
                condition=models.Q(off_discount__gte=0) & models.Q(off_discount__lte=100),
                name="packages_price_history_off_discount_between_zero_and_hundred",
            ),
        ]

    def __str__(self):
        return f"{self.package.code}: {self.price} (-{self.off_discount}%)"
