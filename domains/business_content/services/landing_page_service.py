from django.utils import timezone

from ..models import LandingPage
from .public import public_business_id


class LandingPageService:
    def get_by_slug(self, slug):
        return LandingPage.objects.get(slug=slug, business_id=public_business_id())

    def delete_page(self, instance):
        instance.delete()

    def publish_page(self, instance):
        instance.published_content = instance.draft_content
        instance.status = LandingPage.Status.PUBLISHED
        instance.published_at = timezone.now()
        instance.save()
        return instance
