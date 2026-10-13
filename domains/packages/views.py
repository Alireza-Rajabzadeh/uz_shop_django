from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from core.responses import api_response
from domains.business.models import BusinessProfile
from domains.vendor.auth import VendorJWTAuthentication

from .models import Feature, Package, PackageFeature
from .services import PackageService


class VendorPackageEntitlementView(APIView):
    """What the calling vendor's package makes available.

    The panels fetch this during the splash, so the rules are applied here
    and the payload is codes only — availability is never re-derived in a
    client. A vendor without a business profile reads as the default tier
    instead of failing: the splash must not dead-end an account that simply
    has not created its shop yet.
    """

    authentication_classes = [VendorJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        business = BusinessProfile.objects.filter(vendor=request.user).first()
        package = PackageService.resolve_package(business)
        if package is None:
            # No default tier provisioned: report "no entitlement data"
            # rather than an empty feature list, so the panels show the
            # full menu instead of gating everything off in an
            # environment that has simply not been seeded yet.
            return api_response(data={"package": None, "features": None})
        return api_response(
            data={
                "package": package.code,
                "features": PackageService.features_for(package),
            }
        )


class VendorPackageCatalogView(APIView):
    """Every active package and the features it grants.

    The panels cache this for a long time and answer "which package would
    unlock this feature?" on the client, so a locked menu item can name its
    upgrade without a round trip per feature. This is the map, not the
    caller's answer — availability stays with `/api/packages/me`.

    Packages arrive cheapest-first, and each feature lists the codes of the
    packages granting it in that same order, so the client's "first package
    that has it" is simply the first code in its list. Disabled grants and
    inactive tiers are left out entirely: neither is a real upgrade target.
    """

    authentication_classes = [VendorJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        packages = list(
            Package.objects.filter(is_active=True).order_by("price", "code")
        )

        # feature id -> [(price, code), ...], so each list can be sorted
        # into the same cheapest-first order the packages arrive in.
        granting: dict = {}
        grants = PackageFeature.objects.select_related("package").filter(
            package__is_active=True
        )
        for grant in grants:
            if not grant.config.get("enabled", True):
                continue
            granting.setdefault(grant.feature_id, []).append(
                (grant.package.price, grant.package.code)
            )

        return api_response(
            data={
                "packages": [
                    {"code": package.code, "name": package.name}
                    for package in packages
                ],
                "features": [
                    {
                        "code": feature.code,
                        "name": feature.name,
                        "description": feature.description,
                        "packages": [
                            code
                            for _, code in sorted(granting.get(feature.id, []))
                        ],
                    }
                    for feature in Feature.objects.all().order_by("pk")
                ],
            }
        )
