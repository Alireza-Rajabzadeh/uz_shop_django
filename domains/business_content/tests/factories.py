from domains.business.models import BusinessProfile


def storefront_business():
    """The profile that the unauthenticated delivery routes resolve.

    `inventory.0022` seeds ``BusinessProfile`` id=1 with no vendor, and
    ``public_business_id()`` reads the lowest-pk row — so tests adopt that
    seeded profile as the storefront owner instead of creating a competing
    one. Creating a second profile here would silently make every public
    delivery test read a business that owns no content.
    """
    business = BusinessProfile.objects.first()
    if business is None:
        business = BusinessProfile.objects.create(
            business_name="Storefront",
            display_name="Storefront",
        )
    return business
