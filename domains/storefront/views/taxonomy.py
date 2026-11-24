from django.utils.translation import gettext as _
from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from core.responses import api_response
from domains.content.services.seo_service import SEOService


class StorefrontTaxonomyView(APIView):
    """Customer-facing storefront taxonomy detail & SEO API.

    Returns resource summary (id, slug, name) and SEO for brand or category.
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request, resource_type, slug):
        payload = SEOService.get_public_resource(resource_type, slug)
        if payload is None:
            raise NotFound(_("Taxonomy resource not found."))
        return api_response(True, "", payload)
