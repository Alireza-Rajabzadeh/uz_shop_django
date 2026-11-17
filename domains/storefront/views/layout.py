from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from core.responses import api_response
from domains.storefront.services.layout_service import StorefrontLayoutService


class StorefrontLayoutView(APIView):
    """Customer-facing storefront layout API.

    Returns shared layout configuration (header, categories, footer, theme, config)
    for the resolved tenant or the platform storefront.
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        business = getattr(request, "business", None)
        data = StorefrontLayoutService().resolve_layout(business=business)
        return api_response(True, "", data)
