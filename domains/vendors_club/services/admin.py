"""The admin panel's read surface over the vendor club.

Activities are editable here, but point movements are not: they go through
`PointsService`, the only writer of the ledger and the balances. The queries
below own the filter vocabularies and ordering allowlists so the views stay a
thin HTTP layer over them.
"""

from django.db.models import Count, Q, Sum

from ..models import (
    VendorClubActivity,
    VendorClubMembership,
    VendorClubPointTransaction,
)


def _order(queryset, ordering, default):
    """Apply an allowlisted ordering with a deterministic tiebreaker.

    The allowlist lives in the query serializers; this only adds the `id`
    tiebreaker, keeping pages stable when the requested field has ties.
    """
    ordering = ordering or default
    tiebreaker = "-id" if ordering.startswith("-") else "id"
    if tiebreaker == ordering:
        return queryset.order_by(ordering)
    return queryset.order_by(ordering, tiebreaker)


class AdminClubService:
    """Queries and display writes for the club's admin screens."""

    # --- activities ---------------------------------------------------

    @staticmethod
    def get_activity(activity_id):
        return VendorClubActivity.objects.filter(pk=activity_id).first()

    @staticmethod
    def list_activities(search=None, is_active=None, ordering=None):
        activities = VendorClubActivity.objects.all()
        if search:
            activities = activities.filter(
                Q(code__icontains=search) | Q(name__icontains=search)
            )
        if is_active is not None:
            activities = activities.filter(is_active=is_active)
        return _order(activities, ordering, "id")

    @staticmethod
    def create_activity(**data):
        return VendorClubActivity.objects.create(**data)

    @staticmethod
    def update_activity(activity, **data):
        for field, value in data.items():
            setattr(activity, field, value)
        activity.save()
        return activity

    # --- memberships --------------------------------------------------

    @staticmethod
    def get_membership(membership_id):
        return (
            VendorClubMembership.objects.select_related("vendor")
            .filter(pk=membership_id)
            .first()
        )

    @staticmethod
    def list_memberships(
        vendor_id=None, search=None, has_points=None, ordering=None
    ):
        memberships = VendorClubMembership.objects.select_related(
            "vendor"
        ).annotate(transaction_count=Count("transactions"))
        if vendor_id:
            memberships = memberships.filter(vendor_id=vendor_id)
        if search:
            memberships = memberships.filter(
                Q(vendor__vendor_code__icontains=search)
                | Q(vendor__phone__icontains=search)
                | Q(vendor__first_name__icontains=search)
                | Q(vendor__last_name__icontains=search)
            )
        if has_points is not None:
            if has_points:
                memberships = memberships.filter(
                    Q(lifetime_points__gt=0) | Q(available_points__gt=0)
                )
            else:
                memberships = memberships.filter(
                    lifetime_points=0, available_points=0
                )
        return _order(memberships, ordering, "-lifetime_points")

    # --- ledger -------------------------------------------------------

    @staticmethod
    def get_transaction(transaction_id):
        return (
            VendorClubPointTransaction.objects.select_related(
                "activity", "membership__vendor"
            )
            .filter(pk=transaction_id)
            .first()
        )

    @staticmethod
    def list_transactions(
        vendor_id=None,
        vendor_code=None,
        transaction_type=None,
        activity_id=None,
        activity_code=None,
        reference_type=None,
        reference_id=None,
        search=None,
        created_from=None,
        created_to=None,
        ordering=None,
    ):
        transactions = VendorClubPointTransaction.objects.select_related(
            "activity", "membership__vendor"
        )
        if vendor_id:
            transactions = transactions.filter(membership__vendor_id=vendor_id)
        if vendor_code:
            transactions = transactions.filter(
                membership__vendor__vendor_code=vendor_code
            )
        if transaction_type:
            transactions = transactions.filter(transaction_type=transaction_type)
        if activity_id:
            transactions = transactions.filter(activity_id=activity_id)
        if activity_code:
            transactions = transactions.filter(activity__code=activity_code)
        if reference_type:
            transactions = transactions.filter(reference_type=reference_type)
        if reference_id:
            transactions = transactions.filter(reference_id=reference_id)
        if search:
            transactions = transactions.filter(
                Q(description__icontains=search)
                | Q(reference_id__icontains=search)
                | Q(membership__vendor__vendor_code__icontains=search)
                | Q(membership__vendor__phone__icontains=search)
            )
        if created_from:
            transactions = transactions.filter(created_at__date__gte=created_from)
        if created_to:
            transactions = transactions.filter(created_at__date__lte=created_to)
        return _order(transactions, ordering, "-created_at")

    # --- overview -----------------------------------------------------

    @staticmethod
    def overview():
        """Program-wide totals for the admin dashboard.

        Balances are summed from the cached membership rows rather than
        rebuilt from the ledger: this is a read-only snapshot, and reconciling
        every membership to answer a dashboard would cost far more than the
        numbers are worth. `PointsService.sync_points()` is the endpoint that
        repairs a drifted cache.
        """
        balances = VendorClubMembership.objects.aggregate(
            members=Count("id"),
            lifetime_points=Sum("lifetime_points"),
            available_points=Sum("available_points"),
        )
        ledger = VendorClubPointTransaction.objects.all()
        totals = {
            row["transaction_type"]: row["total"]
            for row in ledger.values("transaction_type").annotate(
                total=Sum("points")
            )
        }
        activity_counts = VendorClubActivity.objects.aggregate(
            total=Count("id"),
            active=Count("id", filter=Q(is_active=True)),
        )
        # Per-activity totals count only `earn` rows: an activity names what a
        # vendor did to earn, and adjustments merely reference one.
        top_activities = list(
            VendorClubActivity.objects.filter(
                transactions__transaction_type=(
                    VendorClubPointTransaction.TransactionType.EARN
                )
            )
            .annotate(
                total_points=Sum("transactions__points"),
                transaction_count=Count("transactions"),
            )
            .order_by("-total_points", "id")
            .values(
                "id",
                "code",
                "name",
                "points",
                "total_points",
                "transaction_count",
            )[:5]
        )
        return {
            "members": balances["members"] or 0,
            "lifetime_points": balances["lifetime_points"] or 0,
            "available_points": balances["available_points"] or 0,
            "transaction_count": ledger.count(),
            "activities": {
                "total": activity_counts["total"] or 0,
                "active": activity_counts["active"] or 0,
            },
            "totals_by_type": {
                code: totals.get(code, 0)
                for code, _label in VendorClubPointTransaction.TransactionType.choices
            },
            "top_activities": top_activities,
        }
