from domains.business.models import BusinessProfile


def public_business_id():
    """Owner used by the unauthenticated delivery routes.

    `BusinessProfile` is a singleton in practice, so the shared storefront has
    exactly one business to read. When none exists yet there is no owner to
    resolve, and the returned ``None`` simply matches nothing, which the views
    already translate into a 404.
    """
    return BusinessProfile.objects.values_list("id", flat=True).first()
