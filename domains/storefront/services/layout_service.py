from django.core.exceptions import ObjectDoesNotExist
from rest_framework.exceptions import NotFound

from domains.business.services import BusinessService
from domains.business_content.services import PageService as BusinessPageService
from domains.catalog.services import CategoryService
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
            data, _ttl = ContentPageService().get_storefront_page(slug="footer")
            return data
        except (ObjectDoesNotExist, NotFound):
            return None

    def _get_business_footer(self, business):
        try:
            data, _ttl = BusinessPageService().get_storefront_page(
                slug="footer", business=business
            )
            return data
        except (ObjectDoesNotExist, NotFound):
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