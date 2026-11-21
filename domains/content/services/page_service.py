from django.utils import timezone

from ..models import Page


class PageService:
    HOME_SLUG = "home"

    def get_by_slug(self, slug):
        return Page.objects.get(slug=slug)

    def get_home_page(self):
        return self.get_by_slug(self.HOME_SLUG)

    def delete_page(self, instance):
        instance.delete()

    def publish_page(self, instance):
        instance.published_content = instance.draft_content
        instance.status = Page.Status.PUBLISHED
        instance.published_at = timezone.now()
        instance.save()
        return instance

    def get_storefront_page(self, slug="home"):
        """Public storefront page retrieval and resolution."""
        from django.core.exceptions import ObjectDoesNotExist
        from django.utils.translation import gettext as _
        from rest_framework.exceptions import NotFound

        from ..serializers.page_content_serializer import PageContentSerializer
        from .landing_page_content_resolver import LandingPageContentResolver

        try:
            page = self.get_home_page() if slug == self.HOME_SLUG else self.get_by_slug(slug)
        except ObjectDoesNotExist as exc:
            raise NotFound(_("Page not found.")) from exc

        if page.status != Page.Status.PUBLISHED:
            raise NotFound(_("Page not found."))

        page.selected_content = LandingPageContentResolver().resolve(
            page.published_content
        )
        return PageContentSerializer(page).data, getattr(page, "cache_ttl", None)
