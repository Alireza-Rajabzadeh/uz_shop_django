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
    """One movement from the caller's own ledger."""

    transaction_type_name = serializers.SerializerMethodField()
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
            "transaction_type",
            "transaction_type_name",
            "points",
            "activity_code",
            "activity_name",
            "reference_type",
            "reference_id",
            "description",
            "created_at",
        ]
        read_only_fields = fields

    def get_transaction_type_name(self, obj):
        return obj.get_transaction_type_display()
