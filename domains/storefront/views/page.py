from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from core.responses import api_response
from domains.business_content.services import PageService as BusinessPageService
from domains.content.services import PageService as ContentPageService


class StorefrontPageView(APIView):
    """Customer-facing storefront page API.

    Returns published page content for platform or business storefronts.
    Defaults to slug 'home'.
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request, slug="home"):
        business = getattr(request, "business", None)
        if business is not None:
            data, _ttl = BusinessPageService().get_storefront_page(
                slug=slug, business=business
            )
        else:
            data, _ttl = ContentPageService().get_storefront_page(slug=slug)

        return api_response(True, "", data)
