from django.db import transaction
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from .cache import invalidate_landing_page, invalidate_page
from .models import LandingPage, Page, SEORecord


def _after_commit(callback):
    callback()
    transaction.on_commit(callback)


@receiver(pre_save, sender=LandingPage)
@receiver(pre_save, sender=Page)
def remember_previous_slug(sender, instance, **kwargs):
    if instance.pk:
        instance._cache_previous_slug = (
            sender.objects.filter(pk=instance.pk).values_list("slug", flat=True).first()
        )


@receiver(pre_save, sender=SEORecord)
def remember_previous_seo_resource(sender, instance, **kwargs):
    if instance.pk:
        instance._cache_previous_resource = sender.objects.filter(pk=instance.pk).values_list(
            "resource_type", "resource_id"
        ).first()


@receiver(post_save, sender=LandingPage)
@receiver(post_delete, sender=LandingPage)
def invalidate_landing_page_cache(sender, instance, **kwargs):
    slugs = {instance.slug, getattr(instance, "_cache_previous_slug", None)} - {None}
    _after_commit(lambda: [invalidate_landing_page(slug) for slug in slugs])


@receiver(post_save, sender=Page)
@receiver(post_delete, sender=Page)
def invalidate_page_cache(sender, instance, **kwargs):
    slugs = {instance.slug, getattr(instance, "_cache_previous_slug", None)} - {None}
    _after_commit(lambda: [invalidate_page(slug) for slug in slugs])


@receiver(post_save, sender=SEORecord)
@receiver(post_delete, sender=SEORecord)
def invalidate_seo_cache(sender, instance, **kwargs):
    resources = {
        (instance.resource_type, instance.resource_id),
        getattr(instance, "_cache_previous_resource", None),
    } - {None}

    def invalidate():
        for resource_type, resource_id in resources:
            model = {"landing_page": LandingPage, "page": Page}.get(resource_type)
            if model is None:
                continue
            slug = model.objects.filter(pk=resource_id).values_list("slug", flat=True).first()
            if slug:
                invalidator = invalidate_landing_page if model is LandingPage else invalidate_page
                invalidator(slug)

    _after_commit(invalidate)
