"""Admin serializers for the vendor club.

Shapes the admin panel exchanges with the club: the earning activities, the
per-vendor memberships, the whole ledger, and a program overview. Nothing here
writes a point movement — the create serializer only validates the request, and
`PointsService.record_transaction` is what touches the ledger.
"""

from django.utils.translation import gettext as _
from rest_framework import serializers

from domains.vendor.models import Vendor

from .models import (
    VendorClubActivity,
    VendorClubMembership,
    VendorClubPointTransaction,
)


# --- activities -------------------------------------------------------


class VendorClubActivitySerializer(serializers.ModelSerializer):
    """An activity as the admin list and detail return it."""

    class Meta:
        model = VendorClubActivity
        fields = [
            "id",
            "code",
            "name",
            "description",
            "points",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class VendorClubActivityCreateSerializer(serializers.ModelSerializer):
    """The editable surface on create. `code` is the caller's contract."""

    points = serializers.IntegerField(min_value=1)

    class Meta:
        model = VendorClubActivity
        fields = ["code", "name", "description", "points", "is_active"]


class VendorClubActivityUpdateSerializer(serializers.ModelSerializer):
    """Update deliberately omits `code`: the model refuses to change it, and
    ledger rows are keyed off it for the life of the program."""

    points = serializers.IntegerField(min_value=1, required=False)

    class Meta:
        model = VendorClubActivity
        fields = ["name", "description", "points", "is_active"]


class VendorClubActivityQuerySerializer(serializers.Serializer):
    search = serializers.CharField(required=False, allow_blank=True)
    is_active = serializers.BooleanField(required=False)
    ordering = serializers.ChoiceField(
        choices=[
            "id",
            "-id",
            "code",
            "-code",
            "name",
            "-name",
            "points",
            "-points",
            "updated_at",
            "-updated_at",
        ],
        required=False,
        allow_blank=True,
    )


# --- memberships ------------------------------------------------------


class VendorClubMembershipSerializer(serializers.ModelSerializer):
    """One vendor's membership and cached balances."""

    vendor_id = serializers.IntegerField(source="vendor.id", read_only=True)
    vendor_code = serializers.CharField(
        source="vendor.vendor_code", read_only=True
    )
    vendor_name = serializers.SerializerMethodField()
    vendor_phone = serializers.CharField(source="vendor.phone", read_only=True)
    transaction_count = serializers.SerializerMethodField()

    class Meta:
        model = VendorClubMembership
        fields = [
            "id",
            "vendor_id",
            "vendor_code",
            "vendor_name",
            "vendor_phone",
            "lifetime_points",
            "available_points",
            "transaction_count",
            "last_synced_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_vendor_name(self, obj):
        return f"{obj.vendor.first_name} {obj.vendor.last_name}".strip()

    def get_transaction_count(self, obj):
        # The list annotates the count; the detail falls back to a query.
        annotated = getattr(obj, "transaction_count", None)
        return annotated if annotated is not None else obj.transactions.count()


class VendorClubMembershipDetailSerializer(VendorClubMembershipSerializer):
    """The membership plus the tail of its ledger, for the admin's drawer."""

    recent_transactions = serializers.SerializerMethodField()

    class Meta(VendorClubMembershipSerializer.Meta):
        fields = VendorClubMembershipSerializer.Meta.fields + [
            "recent_transactions"
        ]

    def get_recent_transactions(self, obj):
        rows = obj.transactions.select_related("activity").order_by(
            "-created_at", "-id"
        )[:10]
        return VendorClubTransactionSerializer(rows, many=True).data


class VendorClubMembershipQuerySerializer(serializers.Serializer):
    search = serializers.CharField(required=False, allow_blank=True)
    has_points = serializers.BooleanField(required=False)
    ordering = serializers.ChoiceField(
        choices=[
            "id",
            "-id",
            "lifetime_points",
            "-lifetime_points",
            "available_points",
            "-available_points",
            "updated_at",
            "-updated_at",
            "created_at",
            "-created_at",
        ],
        required=False,
        allow_blank=True,
    )


# --- ledger -----------------------------------------------------------


class VendorClubTransactionSerializer(serializers.ModelSerializer):
    """One ledger row, seen across every vendor."""

    membership_id = serializers.IntegerField(read_only=True)
    vendor_id = serializers.IntegerField(
        source="membership.vendor.id", read_only=True
    )
    vendor_code = serializers.CharField(
        source="membership.vendor.vendor_code", read_only=True
    )
    vendor_name = serializers.SerializerMethodField()
    transaction_type_name = serializers.SerializerMethodField()
    activity_id = serializers.IntegerField(read_only=True, allow_null=True)
    activity_code = serializers.CharField(
        source="activity.code", read_only=True, allow_null=True
    )
    activity_name = serializers.CharField(
        source="activity.name", read_only=True, allow_null=True
    )

    class Meta:
        model = VendorClubPointTransaction
        fields = [
            "id",
            "membership_id",
            "vendor_id",
            "vendor_code",
            "vendor_name",
            "transaction_type",
            "transaction_type_name",
            "points",
            "activity_id",
            "activity_code",
            "activity_name",
            "reference_type",
            "reference_id",
            "description",
            "created_at",
        ]
        read_only_fields = fields

    def get_vendor_name(self, obj):
        vendor = obj.membership.vendor
        return f"{vendor.first_name} {vendor.last_name}".strip()

    def get_transaction_type_name(self, obj):
        return obj.get_transaction_type_display()


class VendorClubTransactionQuerySerializer(serializers.Serializer):
    """The filter vocabulary `GET /vendors-club/admin/transactions` takes."""

    vendor_id = serializers.IntegerField(required=False, min_value=1)
    vendor_code = serializers.CharField(required=False, allow_blank=True)
    transaction_type = serializers.ChoiceField(
        choices=VendorClubPointTransaction.TransactionType.choices,
        required=False,
        allow_blank=True,
    )
    activity_id = serializers.IntegerField(required=False, min_value=1)
    activity_code = serializers.CharField(required=False, allow_blank=True)
    reference_type = serializers.CharField(required=False, allow_blank=True)
    reference_id = serializers.CharField(required=False, allow_blank=True)
    search = serializers.CharField(required=False, allow_blank=True)
    created_from = serializers.DateField(required=False)
    created_to = serializers.DateField(required=False)
    ordering = serializers.ChoiceField(
        choices=[
            "created_at",
            "-created_at",
            "points",
            "-points",
            "id",
            "-id",
        ],
        required=False,
        allow_blank=True,
    )

    def validate(self, attrs):
        created_from = attrs.get("created_from")
        created_to = attrs.get("created_to")
        if (
            created_from is not None
            and created_to is not None
            and created_from > created_to
        ):
            raise serializers.ValidationError(
                {"created_to": _("Must be on or after the start date.")}
            )
        return attrs


class VendorClubTransactionCreateSerializer(serializers.Serializer):
    """A hand-entered movement. Shape only; the ledger rules live in the
    service, which is what actually records the row."""

    vendor = serializers.PrimaryKeyRelatedField(
        queryset=Vendor.objects.all()
    )
    transaction_type = serializers.ChoiceField(
        choices=VendorClubPointTransaction.TransactionType.choices
    )
    points = serializers.IntegerField(min_value=1)
    activity = serializers.PrimaryKeyRelatedField(
        queryset=VendorClubActivity.objects.all(),
        required=False,
        allow_null=True,
    )
    reference_type = serializers.CharField(
        required=False, allow_null=True, allow_blank=True, max_length=64
    )
    reference_id = serializers.CharField(
        required=False, allow_null=True, allow_blank=True, max_length=64
    )
    description = serializers.CharField(
        required=False, allow_blank=True, default=""
    )

    def validate(self, attrs):
        has_type = bool(attrs.get("reference_type"))
        has_id = bool(attrs.get("reference_id"))
        if has_type != has_id:
            raise serializers.ValidationError(
                {"reference_id": _("A reference needs both a type and an id.")}
            )
        return attrs


# --- overview ---------------------------------------------------------


class VendorClubTopActivitySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    code = serializers.CharField()
    name = serializers.CharField()
    points = serializers.IntegerField()
    total_points = serializers.IntegerField()
    transaction_count = serializers.IntegerField()


class VendorClubOverviewSerializer(serializers.Serializer):
    members = serializers.IntegerField()
    lifetime_points = serializers.IntegerField()
    available_points = serializers.IntegerField()
    transaction_count = serializers.IntegerField()
    activities = serializers.DictField(child=serializers.IntegerField())
    totals_by_type = serializers.DictField(child=serializers.IntegerField())
    top_activities = VendorClubTopActivitySerializer(many=True)
