from rest_framework import serializers
from domains.customer.models import CustomerAddress


class CustomerAddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomerAddress
        fields = [
            "id", "title", "country", "state", "city",
            "postal_code", "address_line1", "address_line2",
            "house_number", "latitude", "longitude", "is_default",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
