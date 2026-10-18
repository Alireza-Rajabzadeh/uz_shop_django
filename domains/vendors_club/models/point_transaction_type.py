from django.db import models


class VendorClubPointTransactionType(models.Model):
    """Reference row for one value of ``VendorClubPointTransaction.transaction_type``.

    Reference data only: the ledger stores the ``code`` itself and never points
    here, so the audit trail stays valid even if the display text is reworded.
    The table exists so the admin and the panels have a place to read a type's
    name and description from, mirroring ``marketplace.PricingStrategy``.

    ``code`` mirrors ``VendorClubPointTransaction.TransactionType`` and is what
    ``PointsService`` reads its direction tables off, so adding a type means
    adding a member to that enum, a row here, and a branch in the service.
    There is deliberately no write path of its own.
    """

    code = models.CharField(max_length=16, unique=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, default="")

    class Meta:
        db_table = "vendors_club_point_transaction_type"
        ordering = ["id"]
        verbose_name_plural = "vendor club point transaction types"

    def __str__(self):
        return self.code
