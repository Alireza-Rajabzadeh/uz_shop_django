from rest_framework import serializers
from domains.customer.models import Customer


class CustomerRegisterSerializer(serializers.Serializer):
    phone = serializers.CharField(required=True, max_length=20)
    first_name = serializers.CharField(required=True, max_length=100)
    last_name = serializers.CharField(required=True, max_length=100)
    email = serializers.EmailField(required=False, allow_blank=True, allow_null=True)
    password = serializers.CharField(required=True, write_only=True, min_length=6)

    def validate_phone(self, value):
        if Customer.objects.filter(phone=value).exists():
            raise serializers.ValidationError("Phone number already registered.")
        return value


class CustomerLoginSerializer(serializers.Serializer):
    phone = serializers.CharField(required=True, max_length=20)
    password = serializers.CharField(required=True, write_only=True)


class CustomerProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = ["id", "phone", "first_name", "last_name", "email", "is_active", "created_at"]
        read_only_fields = ["id", "is_active", "created_at"]
