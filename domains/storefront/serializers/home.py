from rest_framework import serializers

from core.serializers.tenant import BusinessAwareSerializer


class StorefrontHomeSerializer(BusinessAwareSerializer):
    """Serializer for Storefront Home API requests and parameters.

    Inherits from BusinessAwareSerializer so that when a business is resolved
    from the tenant context via TenantMiddleware, its ID takes precedence over
    any client-provided business_id.
    """

    business_id = serializers.IntegerField(required=False, allow_null=True)


class StorefrontHomePageSerializer(serializers.Serializer):
    """Serializer for rendering customer-facing homepage data."""

    id = serializers.IntegerField()
    title = serializers.CharField()
    slug = serializers.CharField()
    status = serializers.CharField()
    content = serializers.JSONField()
    seo = serializers.JSONField(required=False, allow_null=True)
