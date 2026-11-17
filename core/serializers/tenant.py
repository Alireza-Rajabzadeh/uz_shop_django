from rest_framework import serializers


class BusinessAwareSerializer(serializers.Serializer):
    """Serializer base for business-aware APIs.

    If a business is resolved from the tenant context,
    its ID takes precedence over any client-provided business_id.

    Without a resolved business, the client's business_id
    is preserved.
    """

    def to_internal_value(self, data):
        request = self.context.get("request")
        business = getattr(request, "business", None)

        if business is not None:
            data = data.copy()
            data["business_id"] = business.id

        return super().to_internal_value(data)


TenantScopedSerializer = BusinessAwareSerializer
