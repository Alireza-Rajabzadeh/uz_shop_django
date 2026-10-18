from django.db import models
from django.db.models import Q

from .base import TimestampedModel


class VendorClubMembership(TimestampedModel):
    """A vendor's club membership and its current point balances.

    One membership per vendor. `lifetime_points` and `available_points` are a
    projection of `VendorClubPointTransaction`; the ledger is the source of
    truth and this row is only ever a cache of it.

    Other domains must never write these two fields directly. Balances move
    only through `domains.vendors_club.services.PointsService`, which keeps
    every movement in the ledger so the cache can be rebuilt at any time.
    """

    vendor = models.OneToOneField(
        "vendor.Vendor",
        on_delete=models.CASCADE,
        related_name="club_membership",
    )
    lifetime_points = models.PositiveBigIntegerField(default=0)
    available_points = models.PositiveBigIntegerField(default=0)
    last_synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "vendors_club_membership"
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(lifetime_points__gte=0),
                name="vendors_club_membership_lifetime_points_gte_zero",
            ),
            models.CheckConstraint(
                condition=Q(available_points__gte=0),
                name="vendors_club_membership_available_points_gte_zero",
            ),
        ]

    def __str__(self):
        return f"Club membership for {self.vendor.vendor_code}"
