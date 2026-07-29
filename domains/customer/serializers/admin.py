from rest_framework import serializers

from domains.customer.models import Customer, CustomerStatus


class AdminCustomerListQuerySerializer(serializers.Serializer):
    id = serializers.IntegerField(required=False, min_value=1)
    search = serializers.CharField(required=False, allow_blank=True)
    status_id = serializers.IntegerField(required=False, min_value=1)
    gender = serializers.ChoiceField(
        choices=["male", "female", "other"], required=False
    )
    customer_code = serializers.CharField(required=False, allow_blank=True)
    first_name = serializers.CharField(required=False, allow_blank=True)
    last_name = serializers.CharField(required=False, allow_blank=True)
    email = serializers.CharField(required=False, allow_blank=True)
    phone = serializers.CharField(required=False, allow_blank=True)
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


class CustomerStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomerStatus
        fields = ["id", "name", "title", "description", "is_active"]


class AdminCustomerSerializer(serializers.ModelSerializer):
    status_id = serializers.PrimaryKeyRelatedField(
        source="status", queryset=CustomerStatus.objects.all()
    )
    status = CustomerStatusSerializer(read_only=True)

    class Meta:
        model = Customer
        fields = [
            "id", "customer_code", "first_name", "last_name", "email", "phone",
            "status_id", "status", "date_of_birth", "gender", "email_verified_at",
            "phone_verified_at", "last_login", "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "customer_code", "email_verified_at", "phone_verified_at",
            "last_login", "created_at", "updated_at",
        ]
