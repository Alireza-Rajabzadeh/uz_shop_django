from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils.translation import gettext as _
from rest_framework import serializers
from core.utils import PhoneNormalizationError, normalize_phone
from domains.vendor.models import Vendor, VendorPreference


class VendorRegisterSerializer(serializers.Serializer):
    first_name = serializers.CharField(required=True, max_length=100)
    last_name = serializers.CharField(required=True, max_length=100)
    email = serializers.EmailField(required=False, allow_blank=True, allow_null=True)
    phone = serializers.CharField(required=True, max_length=20)
    national_id = serializers.CharField(required=True, max_length=20)
    password = serializers.CharField(required=True, write_only=True, min_length=6)
    password_confirmation = serializers.CharField(write_only=True, required=True)
    date_of_birth = serializers.DateField(required=False, allow_null=True)
    gender = serializers.ChoiceField(
        choices=["male", "female", "other"],
        required=False,
        allow_null=True,
    )

    def validate_phone(self, value):
        try:
            value = normalize_phone(value)
        except PhoneNormalizationError as exc:
            raise serializers.ValidationError(_("Enter a valid mobile number.")) from exc
        if Vendor.objects.filter(phone=value).exists():
            raise serializers.ValidationError(_("Phone number already registered."))
        return value

    def validate_national_id(self, value):
        if Vendor.objects.filter(national_id=value).exists():
            raise serializers.ValidationError(_("National ID already registered."))
        return value

    def validate(self, attrs):
        if attrs["password"] != attrs["password_confirmation"]:
            raise serializers.ValidationError({"password_confirmation": _("Passwords do not match.")})
        return attrs


class VendorRegisterConfirmationSerializer(serializers.Serializer):
    request_id = serializers.CharField(required=True, max_length=64)
    code = serializers.RegexField(r"^[0-9]{6}$", required=True)


class VendorLoginSerializer(serializers.Serializer):
    phone = serializers.CharField(required=True, max_length=20)
    password = serializers.CharField(required=True, write_only=True)

    def validate_phone(self, value):
        try:
            return normalize_phone(value)
        except PhoneNormalizationError as exc:
            raise serializers.ValidationError(_("Enter a valid mobile number.")) from exc


class VendorLoginConfirmationSerializer(serializers.Serializer):
    request_id = serializers.CharField(required=True, max_length=64)
    code = serializers.RegexField(r"^[0-9]{6}$", required=True)


class VendorPhoneConfirmationSerializer(serializers.Serializer):
    request_id = serializers.CharField(required=True, max_length=64)
    code = serializers.RegexField(r"^[0-9]{6}$", required=True)


class VendorPasswordForgotSerializer(serializers.Serializer):
    phone = serializers.CharField(required=True, max_length=20)

    def validate_phone(self, value):
        try:
            return normalize_phone(value)
        except PhoneNormalizationError as exc:
            raise serializers.ValidationError(_("Enter a valid mobile number.")) from exc


class VendorPasswordForgotConfirmationSerializer(serializers.Serializer):
    request_id = serializers.CharField(required=True, max_length=64)
    code = serializers.RegexField(r"^[0-9]{6}$", required=True)
    new_password = serializers.CharField(write_only=True, trim_whitespace=False)
    new_password_confirmation = serializers.CharField(
        write_only=True, trim_whitespace=False
    )

    def validate(self, attrs):
        if attrs["new_password"] != attrs["new_password_confirmation"]:
            raise serializers.ValidationError({
                "new_password_confirmation": _("Passwords do not match.")
            })
        try:
            validate_password(attrs["new_password"])
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"new_password": exc.messages}) from exc
        return attrs


class VendorProfileSerializer(serializers.ModelSerializer):
    status_title = serializers.CharField(source="status.title", read_only=True)

    class Meta:
        model = Vendor
        fields = [
            "id", "vendor_code", "first_name", "last_name", "email", "phone",
            "national_id", "status_title", "date_of_birth", "gender",
            "email_verified_at", "phone_verified_at", "created_at",
        ]
        read_only_fields = [
            "id", "vendor_code", "national_id", "status_title",
            "email_verified_at", "phone_verified_at", "created_at",
        ]


class VendorUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vendor
        fields = [
            "first_name", "last_name", "email", "date_of_birth", "gender",
        ]


class VendorPasswordChangeSerializer(serializers.Serializer):
    current_password = serializers.CharField(
        allow_blank=False, trim_whitespace=False, write_only=True
    )
    new_password = serializers.CharField(
        allow_blank=False, trim_whitespace=False, write_only=True, min_length=6
    )
    new_password_confirmation = serializers.CharField(
        allow_blank=False, trim_whitespace=False, write_only=True
    )

    def validate(self, attrs):
        if attrs["new_password"] != attrs["new_password_confirmation"]:
            raise serializers.ValidationError({
                "new_password_confirmation": _("Password confirmation does not match.")
            })
        return attrs


class VendorPreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = VendorPreference
        fields = [
            "receive_order_emails",
            "receive_sms_notifications",
            "receive_push_notifications",
        ]
