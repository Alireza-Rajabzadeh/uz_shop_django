from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import Package, PackagePriceHistory

# Guards against a receiver registered twice (autoreload, tests importing
# the module under two names), which would double every history row.
RECEIVER_UID = "packages_package_price_history"


def _pricing_changed(previous, package):
    return (
        previous is None
        or previous["price"] != package.price
        or previous["off_discount"] != package.off_discount
    )


@receiver(pre_save, sender=Package, dispatch_uid=f"{RECEIVER_UID}_remember")
def remember_package_pricing(sender, instance, **kwargs):
    """Stash the stored pricing so `post_save` can tell change from no-op.

    A read is cheaper here than in `post_save`, where the row has already
    been overwritten and the old values are gone.
    """
    if instance._state.adding or instance.pk is None:
        instance._previous_pricing = None
        return
    instance._previous_pricing = (
        type(instance).objects.filter(pk=instance.pk)
        .values("price", "off_discount")
        .first()
    )


@receiver(post_save, sender=Package, dispatch_uid=f"{RECEIVER_UID}_record")
def record_package_price_history(sender, instance, created, **kwargs):
    """Append a history row for a new package or a real pricing change.

    This hangs off the model rather than a service or a view so the seeder,
    the Django admin, and any future reservation service all leave the same
    trail. `post_save` runs inside the caller's transaction, so a rollback
    discards the history row together with the price that caused it.
    """
    previous = getattr(instance, "_previous_pricing", None) if not created else None

    if not created and not _pricing_changed(previous, instance):
        # Saving an unrelated field, or re-saving the same pricing, must not
        # invent a history entry.
        return

    PackagePriceHistory.objects.create(
        package=instance,
        price=instance.price,
        off_discount=instance.off_discount,
    )
