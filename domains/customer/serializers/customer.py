from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils.translation import gettext as _
from rest_framework import serializers
from core.utils import PhoneNormalizationError, normalize_phone
from domains.customer.models import Customer, CustomerPreference


class CustomerRegisterSerializer(serializers.Serializer):
    first_name = serializers.CharField(required=True, max_length=100)
    last_name = serializers.CharField(required=True, max_length=100)
    email = serializers.EmailField(required=False, allow_blank=True, allow_null=True)
    phone = serializers.CharField(required=True, max_length=20)
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
        if Customer.objects.filter(phone=value).exists():
            raise serializers.ValidationError(_("Phone number already registered."))
        return value

    def validate(self, attrs):
        if attrs["password"] != attrs["password_confirmation"]:
            raise serializers.ValidationError({"password_confirmation": _("Passwords do not match.")})
        return attrs


class CustomerLoginSerializer(serializers.Serializer):
    phone = serializers.CharField(required=True, max_length=20)
    password = serializers.CharField(required=True, write_only=True)

    def validate_phone(self, value):
        try:
            return normalize_phone(value)
        except PhoneNormalizationError as exc:
            raise serializers.ValidationError(_("Enter a valid mobile number.")) from exc


class CustomerLoginConfirmationSerializer(serializers.Serializer):
    request_id = serializers.CharField(required=True, max_length=64)
    code = serializers.RegexField(r"^[0-9]{6}$", required=True)


class CustomerPhoneConfirmationSerializer(serializers.Serializer):
    request_id = serializers.CharField(required=True, max_length=64)
    code = serializers.RegexField(r"^[0-9]{6}$", required=True)


class CustomerPasswordForgotSerializer(serializers.Serializer):
    phone = serializers.CharField(required=True, max_length=20)

    def validate_phone(self, value):
        try:
            return normalize_phone(value)
        except PhoneNormalizationError as exc:
            raise serializers.ValidationError(_("Enter a valid mobile number.")) from exc


class CustomerPasswordForgotConfirmationSerializer(serializers.Serializer):
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


class CustomerProfileSerializer(serializers.ModelSerializer):
    status_title = serializers.CharField(source="status.title", read_only=True)

    class Meta:
        model = Customer
        fields = [
            "id", "customer_code", "first_name", "last_name", "email", "phone",
            "status_title", "date_of_birth", "gender",
            "email_verified_at", "phone_verified_at", "created_at",
        ]
        read_only_fields = [
            "id", "customer_code", "status_title",
            "email_verified_at", "phone_verified_at", "created_at",
        ]


class CustomerUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = [
            "first_name", "last_name", "email", "date_of_birth", "gender",
        ]


class CustomerPasswordChangeSerializer(serializers.Serializer):
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


class CustomerPreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomerPreference
        fields = [
            "receive_order_emails",
            "receive_sms_notifications",
            "receive_push_notifications",
        ]
