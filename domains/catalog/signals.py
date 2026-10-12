from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .cache import invalidate_categories_cache
from .models import Category


def _after_commit(callback):
    # Same shape as `domains.content.signals`: clear now so a reader cannot
    # repopulate the key from the pre-commit row, then clear again once the
    # write is durable. Both calls are idempotent deletes.
    callback()
    transaction.on_commit(callback)


@receiver(post_save, sender=Category)
@receiver(post_delete, sender=Category)
def invalidate_category_tree_cache(sender, instance, **kwargs):
    # Hooked at the model, not in `CategoryService`, because the tree is
    # also written by seed commands and bulk querysets.
    _after_commit(invalidate_categories_cache)
