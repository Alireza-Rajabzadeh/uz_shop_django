from django.core.exceptions import ObjectDoesNotExist
from rest_framework.exceptions import NotFound

from domains.business.services import BusinessService
from domains.catalog.services import CategoryService


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
        from domains.business.services.business_subdomain_service import (
            BusinessSubdomainService,
        )

        active_sub = BusinessSubdomainService.get_active_subdomain(business)
        subdomain = active_sub.subdomain if active_sub else getattr(business, "subdomain", "")
        business_data = self._get_business_data(business)

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
                    "subdomain": subdomain,
                    "business": business_data,
                },
            },
        }

    def _get_business_data(self, business):
        try:
            from domains.business.api.serializers import (
                PublicBusinessCategorySerializer,
                PublicBusinessPhoneSerializer,
                PublicBusinessProfileSerializer,
                PublicBusinessSocialLinkSerializer,
                PublicBusinessWorkingDaySerializer,
            )

            objects = BusinessService.public_data(business=business)
            profile = objects.get("profile")
            return {
                "profile": (
                    PublicBusinessProfileSerializer(profile).data
                    if profile
                    else None
                ),
                "phones": PublicBusinessPhoneSerializer(
                    objects.get("phones", []), many=True
                ).data,
                "social_links": PublicBusinessSocialLinkSerializer(
                    objects.get("social_links", []), many=True
                ).data,
                "working_hours": PublicBusinessWorkingDaySerializer(
                    objects.get("working_hours", []), many=True
                ).data,
                "categories": PublicBusinessCategorySerializer(
                    objects.get("categories", []), many=True
                ).data,
            }
        except Exception:
            return None

    def _get_platform_footer(self):
        try:
            from domains.content.services import PageService as ContentPageService

            data, _ttl = ContentPageService().get_storefront_page(slug="footer")
            return data
        except (ObjectDoesNotExist, NotFound):
            return None

    def _get_business_footer(self, business):
        try:
            from domains.business_content.services import PageService as BusinessPageService

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