from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import F, Q, Sum
from django.utils import timezone

from ..models import (
    VendorClubActivity,
    VendorClubMembership,
    VendorClubPointTransaction,
)


DEFAULT_SYNC_INTERVAL_SECONDS = 24 * 60 * 60


class AwardStatus:
    """Why `award_points` did or did not move a balance."""

    AWARDED = "awarded"
    DUPLICATE = "duplicate"
    INACTIVE = "inactive"
    NOT_FOUND = "not_found"


class AwardResult:
    """Outcome of one `award_points` call.

    `status` is an `AwardStatus` value. `points`, `membership`, and
    `transaction` are populated as far as the outcome allows: an inactive or
    unknown activity leaves all three empty, a duplicate leaves the existing
    membership and no transaction, and an award fills all three.
    """

    def __init__(self, status, *, points=0, membership=None, transaction=None):
        self.status = status
        self.points = points
        self.membership = membership
        self.transaction = transaction

    @property
    def awarded(self):
        return self.status == AwardStatus.AWARDED

    def __repr__(self):
        return f"<AwardResult status={self.status} points={self.points}>"


class SyncResult:
    """Outcome of reconciling one membership from the ledger."""

    def __init__(self, membership, *, repaired):
        self.membership = membership
        self.lifetime_points = membership.lifetime_points
        self.available_points = membership.available_points
        self.repaired = repaired

    def __repr__(self):
        return (
            f"<SyncResult membership={self.membership.pk} "
            f"repaired={self.repaired}>"
        )


class PointsService:
    """The only writer of membership balances and the point ledger.

    Other domains must call this service; they must never update
    `VendorClubMembership.lifetime_points` / `available_points` or insert
    `VendorClubPointTransaction` rows directly. Keeping every movement in one
    place is what lets `sync_points` rebuild the balances from the ledger at
    any time.

    `points` on a transaction is always positive, so its `transaction_type`
    carries the sign. The two direction tables below are the single source of
    truth for that sign, and both the incremental update on award and the full
    reconciliation read from them, so the two paths can never disagree.

    Only `EARN` is produced today. `SPEND`, `ADJUSTMENT`, and `REVERSAL` are
    mapped carefully so reconciliation stays correct if and when the
    workflows that write them are added:

    ============  ============  =============
    type          lifetime      available
    ============  ============  =============
    earn          + points      + points
    adjustment     0            + points
    spend          0            - points
    reversal      - points      - points
    ============  ============  =============
    """

    TransactionType = VendorClubPointTransaction.TransactionType

    LIFETIME_DIRECTION = {
        TransactionType.EARN: 1,
        TransactionType.ADJUSTMENT: 0,
        TransactionType.SPEND: 0,
        TransactionType.REVERSAL: -1,
    }
    AVAILABLE_DIRECTION = {
        TransactionType.EARN: 1,
        TransactionType.ADJUSTMENT: 1,
        TransactionType.SPEND: -1,
        TransactionType.REVERSAL: -1,
    }

    # --- awarding -----------------------------------------------------

    @classmethod
    @transaction.atomic
    def award_points(
        cls,
        *,
        vendor,
        activity_code,
        reference_type=None,
        reference_id=None,
        description="",
    ):
        """Award the activity's points to a vendor.

        The activity is looked up by `code`; a missing or inactive activity
        awards nothing. The transaction row and the balance update commit
        together or not at all.

        Idempotency is a database guarantee, not this method's bookkeeping:
        the partial unique index `vendors_club_point_tx_earn_unique` allows
        one `EARN` per `(membership, activity, reference_type, reference_id)`.
        A repeat call carrying the same reference therefore returns
        `AwardStatus.DUPLICATE`. Awards with no reference are not deduplicated.
        """
        activity = VendorClubActivity.objects.filter(code=activity_code).first()
        if activity is None:
            return AwardResult(AwardStatus.NOT_FOUND)
        if not activity.is_active:
            return AwardResult(AwardStatus.INACTIVE)

        # `get_or_create` on a locked queryset both serialises awards for this
        # vendor and survives the race where two requests create the
        # membership at once (Django retries the read on IntegrityError).
        membership, _ = VendorClubMembership.objects.select_for_update().get_or_create(
            vendor=vendor
        )

        # Cheap duplicate check; the unique index below is the real authority
        # and still catches this under concurrency.
        if reference_id is not None and membership.transactions.filter(
            transaction_type=cls.TransactionType.EARN,
            activity=activity,
            reference_type=reference_type,
            reference_id=reference_id,
        ).exists():
            return AwardResult(AwardStatus.DUPLICATE, membership=membership)

        try:
            # Nested atomic creates a savepoint: a rejected duplicate rolls
            # back only this insert and leaves the outer transaction usable.
            with transaction.atomic():
                entry = VendorClubPointTransaction.objects.create(
                    membership=membership,
                    activity=activity,
                    transaction_type=cls.TransactionType.EARN,
                    points=activity.points,
                    reference_type=reference_type,
                    reference_id=reference_id,
                    description=description,
                )
        except IntegrityError:
            return AwardResult(AwardStatus.DUPLICATE, membership=membership)

        cls._apply(entry)
        membership.refresh_from_db(
            fields=["lifetime_points", "available_points"]
        )
        return AwardResult(
            AwardStatus.AWARDED,
            points=activity.points,
            membership=membership,
            transaction=entry,
        )

    @classmethod
    def _apply(cls, entry):
        """Move a locked membership's balances by one ledger entry.

        `update()` with `F()` runs the arithmetic in the database, so
        concurrent awards add to the stored value instead of overwriting it.
        """
        lifetime_delta, available_delta = cls._deltas(
            entry.transaction_type, entry.points
        )
        VendorClubMembership.objects.filter(pk=entry.membership_id).update(
            lifetime_points=F("lifetime_points") + lifetime_delta,
            available_points=F("available_points") + available_delta,
        )

    # --- reconciliation ----------------------------------------------

    @classmethod
    def sync_points(cls, membership=None):
        """Rebuild balances from the ledger.

        Pass one membership to reconcile it, or omit the argument to
        reconcile every membership. `last_synced_at` is stamped only after
        the recomputed balances commit.
        """
        if membership is not None:
            return cls._reconcile(membership.pk)
        return [
            cls._reconcile(membership_id)
            for membership_id in VendorClubMembership.objects.values_list(
                "id", flat=True
            )
        ]

    @classmethod
    @transaction.atomic
    def _reconcile(cls, membership_id):
        membership = VendorClubMembership.objects.select_for_update().get(
            pk=membership_id
        )
        lifetime, available = cls._ledger_totals(membership)
        repaired = (
            membership.lifetime_points != lifetime
            or membership.available_points != available
        )

        membership.lifetime_points = lifetime
        membership.available_points = available
        membership.last_synced_at = timezone.now()
        membership.save(
            update_fields=[
                "lifetime_points",
                "available_points",
                "last_synced_at",
                "updated_at",
            ]
        )
        return SyncResult(membership, repaired=repaired)

    @classmethod
    def _ledger_totals(cls, membership):
        lifetime = 0
        available = 0
        rows = membership.transactions.values_list(
            "transaction_type", "points"
        ).iterator()
        for transaction_type, points in rows:
            lifetime_delta, available_delta = cls._deltas(
                transaction_type, points
            )
            lifetime += lifetime_delta
            available += available_delta
        return lifetime, available

    @classmethod
    def _deltas(cls, transaction_type, points):
        return (
            points * cls.LIFETIME_DIRECTION.get(transaction_type, 0),
            points * cls.AVAILABLE_DIRECTION.get(transaction_type, 0),
        )

    @classmethod
    def is_reconciliation_due(cls, membership):
        interval = cls.reconciliation_interval()
        if interval <= timedelta(0):
            return True
        if membership.last_synced_at is None:
            return True
        return timezone.now() - membership.last_synced_at >= interval

    @classmethod
    def due_memberships(cls):
        """Memberships whose cached balances need a rebuild."""
        interval = cls.reconciliation_interval()
        queryset = VendorClubMembership.objects.all()
        if interval <= timedelta(0):
            return queryset
        cutoff = timezone.now() - interval
        return queryset.filter(
            Q(last_synced_at__lt=cutoff) | Q(last_synced_at__isnull=True)
        )

    @staticmethod
    def reconciliation_interval():
        return timedelta(
            seconds=getattr(
                settings,
                "VENDORS_CLUB_SYNC_INTERVAL_SECONDS",
                DEFAULT_SYNC_INTERVAL_SECONDS,
            )
        )

    # --- reading ------------------------------------------------------

    @classmethod
    def get_membership(cls, vendor, *, force_sync=False):
        """The vendor's membership with current balances.

        Creates the membership on first use. A normal award already updated
        the balances incrementally, so they are trusted unless the cached
        snapshot is older than `VENDORS_CLUB_SYNC_INTERVAL_SECONDS`, in which
        case they are rebuilt from the ledger before being returned. Pass
        `force_sync=True` to rebuild regardless.
        """
        membership, _ = VendorClubMembership.objects.get_or_create(vendor=vendor)
        if force_sync or cls.is_reconciliation_due(membership):
            return cls._reconcile(membership.pk).membership
        return membership

    @classmethod
    def summary(cls, vendor):
        """The vendor's balances plus aggregates over their own ledger.

        Balances come through `get_membership`, so they are reconciled the
        same way the membership endpoint reports them. The per-type totals
        count the *magnitude* stored on each row; the transaction type
        carries the sign.
        """
        membership = cls.get_membership(vendor)
        ledger = membership.transactions
        totals = {
            row["transaction_type"]: row["total"]
            for row in ledger.values("transaction_type").annotate(
                total=Sum("points")
            )
        }
        return {
            "lifetime_points": membership.lifetime_points,
            "available_points": membership.available_points,
            "transaction_count": ledger.count(),
            "totals_by_type": {
                code: totals.get(code, 0)
                for code, _label in cls.TransactionType.choices
            },
            "last_activity_at": ledger.order_by("-created_at", "-id")
            .values_list("created_at", flat=True)
            .first(),
            "member_since": membership.created_at,
            "last_synced_at": membership.last_synced_at,
        }
