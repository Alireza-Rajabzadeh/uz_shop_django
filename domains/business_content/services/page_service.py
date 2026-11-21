from django.utils import timezone

from domains.packages.services import PackageService

from ..models import Page
from .landing_page_content_resolver import LandingPageContentResolver
from .public import public_business_id


class PageService:
    HOME_SLUG = "home"

    def get_by_slug(self, slug, business_id=None):
        return Page.objects.get(slug=slug, business_id=public_business_id(business_id))

    def get_home_page(self, business_id=None):
        return self.get_by_slug(self.HOME_SLUG, business_id=business_id)

    def allows_custom_homepage(self, business):
        """Check whether the business's package/subscription allows custom homepage content."""
        if business is None:
            return False
        package = PackageService.resolve_package(business)
        if package is None:
            # When no default tier exists, fail open as documented in packages domain
            return True
        if not package.is_active:
            return False
        return True

    def is_content_valid_for_rendering(self, content):
        """Validate that the content structure is available and valid for public rendering."""
        if content in ({}, None):
            return True
        if not isinstance(content, dict):
            return False
        components = content.get("components")
        if components is not None and not isinstance(components, list):
            return False
        return True

    def get_published_home_page(self, business):
        """Retrieve the published homepage for a business if one exists."""
        if business is None:
            return None
        return Page.objects.filter(
            business=business,
            slug=self.HOME_SLUG,
            status=Page.Status.PUBLISHED,
        ).first()

    def resolve_home_page_data(self, page):
        """Resolve model references and serialize the published page content."""
        from ..serializers.page_content_serializer import PageContentSerializer

        page.selected_content = LandingPageContentResolver().resolve(
            page.published_content
        )
        return PageContentSerializer(page).data, page.cache_ttl

    def delete_page(self, instance):
        instance.delete()

    def publish_page(self, instance):
        instance.published_content = instance.draft_content
        instance.status = Page.Status.PUBLISHED
        instance.published_at = timezone.now()
        instance.save()
        return instance

    def get_storefront_page(self, slug="home", business=None):
        """Public storefront page retrieval and resolution for business context."""
        from django.core.exceptions import ObjectDoesNotExist
        from django.utils.translation import gettext as _
        from rest_framework.exceptions import NotFound

        if slug == self.HOME_SLUG:
            if not self.allows_custom_homepage(business):
                raise NotFound(_("Page not found."))
            page = self.get_published_home_page(business)
            if page is None:
                raise NotFound(_("Page not found."))
            if not self.is_content_valid_for_rendering(page.published_content):
                raise NotFound(_("Page not found."))
            return self.resolve_home_page_data(page)

        try:
            page = self.get_by_slug(slug, business_id=getattr(business, "id", business))
        except ObjectDoesNotExist as exc:
            raise NotFound(_("Page not found.")) from exc

        if getattr(page, "status", None) != Page.Status.PUBLISHED:
            raise NotFound(_("Page not found."))

        if not self.is_content_valid_for_rendering(page.published_content):
            raise NotFound(_("Page not found."))

        return self.resolve_home_page_data(page)
