"""Entitlement denials for the packages domain.

Kept together because the status code and the rule that raises it are one
contract: an ordinary tier decision must not look like a dead session.

The rules fail open only when the environment has no default tier at all
(``resolve_package`` returns ``None``). That state means the packages data
was never provisioned — a freshly migrated database before ``seed`` — and
there is nothing to enforce; denying every seller action there would brick
the deployment. As soon as a tier exists, a missing or disabled grant is a
real denial.
"""

from django.utils.translation import gettext as _
from rest_framework.exceptions import APIException, ValidationError

from .services import PackageService


class FeatureNotAvailable(APIException):
    """The caller's package does not include the requested feature.

    Deliberately 402 rather than 403: the panels treat 401/403 as session
    invalidation and log the vendor out, while this is an ordinary
    "upgrade to get this" answer. It flows through
    `core.exceptions.custom_exception_handler` into the standard envelope
    like any other DRF exception.
    """

    status_code = 402
    default_detail = _("This feature is not available in your package.")
    default_code = "feature_not_available"


def require_feature(business, code):
    """Raise 402 unless ``business`` may use ``code``; return the grant.

    Returns ``None`` — denying nothing — when no default tier exists to
    enforce. Views call this after resolving their business; the check
    lives in the view body as well as in `permissions.RequiresFeature`
    because some rules are not a yes/no answer.
    """
    package = PackageService.resolve_package(business)
    if package is None:
        return None
    if not package.is_active:
        raise FeatureNotAvailable()
    grant = package.package_features.select_related("feature").filter(
        feature__code=code
    ).first()
    if grant is None or not grant.config.get("enabled", True):
        raise FeatureNotAvailable()
    return grant


def require_capacity(business, code, current):
    """Gate a count-based action beyond the caller's baseline.

    The caller decides what the baseline is (one location, one row, …) and
    only calls this once the baseline is exceeded: from there the feature
    must be available and its ``limit`` must not be reached yet. A feature
    granted without a ``limit`` stays unbounded — no maximum is invented
    here.
    """
    grant = require_feature(business, code)
    if grant is None:
        return None
    limit = grant.config.get("limit")
    if isinstance(limit, int) and current >= limit:
        raise ValidationError(
            _("You have reached the limit of %(limit)s for this feature.")
            % {"limit": limit}
        )
    return grant
