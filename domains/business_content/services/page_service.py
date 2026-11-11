from django.utils import timezone

from ..models import Page
from .public import public_business_id


class PageService:
    HOME_SLUG = "home"

    def get_by_slug(self, slug):
        return Page.objects.get(slug=slug, business_id=public_business_id())

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
