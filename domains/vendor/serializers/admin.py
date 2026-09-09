from rest_framework import serializers

from core.utils import PhoneNormalizationError, normalize_phone
from domains.vendor.models import Vendor, VendorStatus


class AdminVendorListQuerySerializer(serializers.Serializer):
    id = serializers.IntegerField(required=False, min_value=1)
    search = serializers.CharField(required=False, allow_blank=True)
    status_id = serializers.IntegerField(required=False, min_value=1)
    gender = serializers.ChoiceField(
        choices=["male", "female", "other"], required=False
    )
    vendor_code = serializers.CharField(required=False, allow_blank=True)
    first_name = serializers.CharField(required=False, allow_blank=True)
    last_name = serializers.CharField(required=False, allow_blank=True)
    email = serializers.CharField(required=False, allow_blank=True)
    phone = serializers.CharField(required=False, allow_blank=True)
    national_id = serializers.CharField(required=False, allow_blank=True)
    date_of_birth_from = serializers.DateField(required=False)
    date_of_birth_to = serializers.DateField(required=False)
    email_verified = serializers.BooleanField(required=False)
    phone_verified = serializers.BooleanField(required=False)
    has_logged_in = serializers.BooleanField(required=False)
    last_login_from = serializers.DateField(required=False)
    last_login_to = serializers.DateField(required=False)
    created_at_from = serializers.DateField(required=False)
    created_at_to = serializers.DateField(required=False)
    updated_at_from = serializers.DateField(required=False)
    updated_at_to = serializers.DateField(required=False)
    ordering = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        errors = {}
        for prefix in ("date_of_birth", "last_login", "created_at", "updated_at"):
            from_field = f"{prefix}_from"
            to_field = f"{prefix}_to"
            if (
                attrs.get(from_field) is not None
                and attrs.get(to_field) is not None
                and attrs[from_field] > attrs[to_field]
            ):
                errors[to_field] = "Must be on or after the start date."
        if errors:
            raise serializers.ValidationError(errors)
        return attrs


class VendorStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = VendorStatus
        fields = ["id", "name", "title", "description", "is_active"]


class AdminVendorSerializer(serializers.ModelSerializer):
    status_id = serializers.PrimaryKeyRelatedField(
        source="status", queryset=VendorStatus.objects.all()
    )
    status = VendorStatusSerializer(read_only=True)

    class Meta:
        model = Vendor
        fields = [
            "id", "vendor_code", "first_name", "last_name", "email", "phone",
            "national_id", "status_id", "status", "date_of_birth", "gender",
            "email_verified_at", "phone_verified_at", "last_login",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "vendor_code", "email_verified_at", "phone_verified_at",
            "last_login", "created_at", "updated_at",
        ]

    def validate_phone(self, value):
        try:
            value = normalize_phone(value)
        except PhoneNormalizationError as exc:
            raise serializers.ValidationError("Enter a valid mobile number.") from exc
        duplicates = Vendor.objects.filter(phone=value)
        if self.instance is not None:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise serializers.ValidationError("A vendor with this phone already exists.")
        return value
