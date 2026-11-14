from domains.business.models import BusinessProfile


def public_business_id(business_id=None):
    """Owner used by the unauthenticated delivery routes.

    When business_id is provided (e.g. from tenant resolution context), it is
    used directly. Otherwise, it falls back to the first available BusinessProfile.
    """
    if business_id is not None:
        return business_id
    return BusinessProfile.objects.values_list("id", flat=True).first()
