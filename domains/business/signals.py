from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .cache import invalidate_business_cache
from .models import BusinessPhone, BusinessProfile, BusinessSocialLink, BusinessWorkingDay


@receiver(post_save, sender=BusinessProfile)
@receiver(post_delete, sender=BusinessProfile)
@receiver(post_save, sender=BusinessPhone)
@receiver(post_delete, sender=BusinessPhone)
@receiver(post_save, sender=BusinessSocialLink)
@receiver(post_delete, sender=BusinessSocialLink)
@receiver(post_save, sender=BusinessWorkingDay)
@receiver(post_delete, sender=BusinessWorkingDay)
def schedule_business_cache_invalidation(**kwargs):
    transaction.on_commit(invalidate_business_cache)
