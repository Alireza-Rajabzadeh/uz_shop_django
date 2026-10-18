from rest_framework import serializers

from domains.vendors_club.models import (
    VendorClubMembership,
    VendorClubPointTransaction,
)


class VendorClubMembershipSerializer(serializers.ModelSerializer):
    """The caller's own balances. Read-only: nothing here is writable."""

    class Meta:
        model = VendorClubMembership
        fields = [
            "lifetime_points",
            "available_points",
            "last_synced_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class VendorClubTransactionSerializer(serializers.ModelSerializer):
    """One movement from the caller's own ledger.

    `*_points_after` are annotations the view attaches by walking the
    membership's full ledger, so a balance stays correct even when the list is
    filtered down to a subset of rows.
    """

    transaction_type_name = serializers.SerializerMethodField()
    activity_code = serializers.CharField(
        source="activity.code", read_only=True, allow_null=True
    )
    activity_name = serializers.CharField(
        source="activity.name", read_only=True, allow_null=True
    )
    lifetime_points_after = serializers.IntegerField(read_only=True)
    available_points_after = serializers.IntegerField(read_only=True)

    class Meta:
        model = VendorClubPointTransaction
        fields = [
            "id",
            "transaction_type",
            "transaction_type_name",
            "points",
            "activity_code",
            "activity_name",
            "reference_type",
            "reference_id",
            "description",
            "lifetime_points_after",
            "available_points_after",
            "created_at",
        ]
        read_only_fields = fields

    def get_transaction_type_name(self, obj):
        return obj.get_transaction_type_display()


class VendorClubTransactionQuerySerializer(serializers.Serializer):
    """The filter vocabulary `GET /vendor/club/transactions` understands."""

    ordering = serializers.ChoiceField(
        choices=["created_at", "-created_at", "points", "-points"],
        required=False,
        allow_blank=True,
    )
    transaction_type = serializers.ChoiceField(
        choices=VendorClubPointTransaction.TransactionType.choices,
        required=False,
        allow_blank=True,
    )
    activity = serializers.CharField(required=False, allow_blank=True)
    created_from = serializers.DateField(required=False)
    created_to = serializers.DateField(required=False)

    def validate(self, attrs):
        created_from = attrs.get("created_from")
        created_to = attrs.get("created_to")
        if (
            created_from is not None
            and created_to is not None
            and created_from > created_to
        ):
            raise serializers.ValidationError(
                {"created_to": "Must be on or after the start date."}
            )
        return attrs


class VendorClubSummarySerializer(serializers.Serializer):
    """Aggregates over the caller's balances and ledger."""

    lifetime_points = serializers.IntegerField()
    available_points = serializers.IntegerField()
    transaction_count = serializers.IntegerField()
    totals_by_type = serializers.DictField(child=serializers.IntegerField())
    last_activity_at = serializers.DateTimeField(allow_null=True)
    member_since = serializers.DateTimeField()
    last_synced_at = serializers.DateTimeField(allow_null=True)
