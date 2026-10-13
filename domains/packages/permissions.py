from rest_framework.permissions import BasePermission

from domains.business.models import BusinessProfile

from .exceptions import require_feature


class RequiresFeature(BasePermission):
    """Deny unless the caller's package grants ``feature_code``.

    Subclasses set the code. Declaration order matters: list it after
    `IsAuthenticated` so an anonymous caller is a 401, never a tier
    decision, and never a 403 (which the panels read as a dead session).
    """

    feature_code = None

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        business = BusinessProfile.objects.filter(vendor=request.user).first()
        if business is None:
            # A vendor without a profile keeps whatever behaviour the view
            # already has for that state; there is no tier to deny yet.
            return True
        require_feature(business, self.feature_code)
        return True


class RequiresShopProducts(RequiresFeature):
    feature_code = "shop.products"


class RequiresShopOrders(RequiresFeature):
    feature_code = "shop.orders"


class RequiresContentLandingPage(RequiresFeature):
    feature_code = "content.landingpage"
