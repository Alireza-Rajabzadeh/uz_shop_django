from enum import Enum


class BusinessSubdomainEnum(Enum):
    """Lifecycle statuses for business subdomains.

    ACTIVE: The current active subdomain of a business.
    REDIRECT: A historical subdomain that redirects to the business's current subdomain.
    RESERVED: A subdomain reserved by the platform that cannot be used as a public storefront.
    """

    ACTIVE = 1
    REDIRECT = 2
    RESERVED = 3


# Alias for snake_case naming requirement
business_subdomain_enum = BusinessSubdomainEnum
