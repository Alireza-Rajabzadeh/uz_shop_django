from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from .activity import VendorClubActivity
from .membership import VendorClubMembership


class VendorClubPointTransactionQuerySet(models.QuerySet):
    """Append-only queryset: the ledger may never be edited or deleted.

    `save()`/`delete()` on the model guard single rows; this guards the bulk
    `QuerySet.update()`/`QuerySet.delete()` paths that bypass the model.
    """

    def update(self, **kwargs):
        raise ValidationError(
            _("Point transactions are immutable; record a new transaction instead.")
        )

    def delete(self):
        raise ValidationError(
            _("Point transactions are immutable; record a reversal instead.")
        )


class VendorClubPointTransaction(models.Model):
    """An immutable ledger row for one points movement.

    Rows are only ever inserted. A correction is a new `REVERSAL`/`ADJUSTMENT`
    row, never an edit or a delete, so the balance can always be rebuilt from
    the history.

    Duplicate awards are prevented in the database: for an `EARN` tied to a
    source entity, `(membership, activity, reference_type, reference_id)` is
    unique. Manual rows with no reference stay unconstrained.

    `transaction_type` stores the code itself rather than pointing at
    `VendorClubPointTransactionType`, so the audit trail never moves when that
    reference table's display text changes.
    """

    class TransactionType(models.TextChoices):
        EARN = "earn", "Earn"
        SPEND = "spend", "Spend"
        ADJUSTMENT = "adjustment", "Adjustment"
        REVERSAL = "reversal", "Reversal"

    objects = VendorClubPointTransactionQuerySet.as_manager()

    membership = models.ForeignKey(
        VendorClubMembership,
        on_delete=models.PROTECT,
        related_name="transactions",
    )
    activity = models.ForeignKey(
        VendorClubActivity,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="transactions",
    )
    transaction_type = models.CharField(
        max_length=16,
        choices=TransactionType.choices,
    )
    points = models.PositiveIntegerField()
    reference_type = models.CharField(max_length=64, null=True, blank=True)
    reference_id = models.CharField(max_length=64, null=True, blank=True)
    description = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "vendors_club_point_transaction"
        # Chronological: the oldest row is the first movement and every row
        # below it is the path the balance took to get here.
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(
                fields=["membership", "created_at"],
                name="vcpt_membership_created_idx",
            ),
            models.Index(fields=["activity"], name="vcpt_activity_idx"),
            models.Index(
                fields=["reference_type", "reference_id"],
                name="vcpt_reference_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(points__gt=0),
                name="vendors_club_point_tx_points_gt_zero",
            ),
            # A source reference is a type + id pair, or neither: half a
            # reference is never meaningful.
            models.CheckConstraint(
                condition=(
                    Q(reference_type__isnull=True, reference_id__isnull=True)
                    | Q(reference_type__isnull=False, reference_id__isnull=False)
                ),
                name="vendors_club_point_tx_reference_pair",
            ),
            # Idempotency for automatic awards: one earn per source entity per
            # activity per membership. The `earn` literal is
            # `TransactionType.EARN`; a nested class body cannot see the
            # enclosing class namespace, so the value is spelled out here.
            models.UniqueConstraint(
                fields=[
                    "membership",
                    "activity",
                    "reference_type",
                    "reference_id",
                ],
                condition=Q(transaction_type="earn", reference_id__isnull=False),
                name="vendors_club_point_tx_earn_unique",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValidationError(
                _(
                    "Point transactions are immutable; record a new transaction instead."
                )
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError(
            _("Point transactions are immutable; record a reversal instead.")
        )

    def __str__(self):
        return (
            f"{self.get_transaction_type_display()} "
            f"{self.points} for membership {self.membership_id}"
        )
