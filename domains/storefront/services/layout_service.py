from django.core.exceptions import ObjectDoesNotExist

from domains.business.services import BusinessService
from domains.business_content.serializers import (
    PageContentSerializer as BusinessPageContentSerializer,
)
from domains.business_content.services import (
    LandingPageContentResolver as BusinessLandingPageContentResolver,
)
from domains.business_content.services import PageService as BusinessPageService
from domains.catalog.services import CategoryService
from domains.content.serializers import (
    PageContentSerializer as ContentPageContentSerializer,
)
from domains.content.services import (
    LandingPageContentResolver as ContentLandingPageContentResolver,
)
from domains.content.services import PageService as ContentPageService


class StorefrontLayoutService:
    """Resolve layout configuration for platform and business storefronts."""

    def resolve_layout(self, business=None):
        categories = CategoryService().get_storefront_tree()
        if business is None:
            return {
                "header": {},
                "categories": categories,
                "footer": self._get_platform_footer(),
                "theme": {},
                "config": {
                    "is_platform": True,
                    "tenant": None,
                },
            }
        profile_categories = BusinessService.profile_categories(business)
        allowed_ids = set(
            profile_categories.values_list("category_id", flat=True)
        )
        return {
            "header": self._get_business_header(business),
            "categories": [
                category
                for category in categories
                if category["id"] in allowed_ids
            ],
            "footer": self._get_business_footer(business),
            "theme": {},
            "config": {
                "is_platform": False,
                "tenant": {
                    "id": business.id,
                    "business_name": getattr(business, "business_name", ""),
                    "subdomain": getattr(business, "subdomain", ""),
                },
            },
        }

    def _get_platform_footer(self):
        try:
            page = ContentPageService().get_by_slug("footer")
            if page.status != "published":
                return None
            page.selected_content = ContentLandingPageContentResolver().resolve(
                page.published_content
            )
            return ContentPageContentSerializer(page).data
        except ObjectDoesNotExist:
            return None

    def _get_business_footer(self, business):
        service = BusinessPageService()
        try:
            page = service.get_by_slug("footer", business_id=business.id)
            if page.status != "published":
                return None
            if not service.is_content_valid_for_rendering(page.published_content):
                return None
            page.selected_content = BusinessLandingPageContentResolver().resolve(
                page.published_content
            )
            return BusinessPageContentSerializer(page).data
        except ObjectDoesNotExist:
            return None

    def _get_business_header(self, business):
        profile = BusinessService.public_data(business).get("profile")
        if not profile:
            return {}
        return {
            "business_id": profile.id,
            "business_name": getattr(profile, "business_name", ""),
            "avatar": getattr(profile, "avatar", None),
            "cover": getattr(profile, "cover", None),
        }