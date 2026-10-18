"""Project-wide gate for the business lifecycle status.

Vendors are the only principals whose access depends on an admin-managed
state: a registration that still awaits confirmation, and bans. Checking
it here — once, against the verified token's `user_type` claim — covers
every vendor request in the project, present and future, without a
per-view permission someone can forget to add.

Reads are gated alongside writes. The panel caches `businessStatus` on the
client so an ordinary visit costs no request, which means the shell can
keep asking for things while it still believes a status the admin has
since changed; the server is what makes that cache safe to trust. What
differs per status is therefore the allowlist, not the HTTP method.

The check fails open wherever it is not certain: a missing or undecodable
bearer token passes (DRF still owns authentication and answers 401
itself), non-vendor principals pass by construction, and a vendor with no
business yet passes so the registration write can run.

Denials answer 403 in the house envelope with the codes
`business_banned` / `business_confirmation_await` — account state, not
entitlement, so deliberately distinct from the packages domain's 402.
"""

from django.http import JsonResponse
from django.utils.translation import gettext as _
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken

from domains.business.enums.BusinessStatusEnum import BusinessStatusEnum

BEARER_PREFIX = "Bearer "
VENDOR_USER_TYPE = "vendor"

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

# The boot reads the panel performs before its status gate can render an
# explanation: identity, the package payload the gate renders on, and the
# status itself. Denying any of them fails open (`BusinessStatusGate`
# falls back to "active") or hides the notice behind a retry screen, so
# both statuses keep them — the point is to say no, not to be mute.
#
# Safe methods only: exempting the path outright would hand a banned
# vendor a writable `/business/profile` under cover of the status read.
BOOT_PATHS = frozenset(
    {
        "/api/vendor/me",
        "/api/packages/me",
        "/api/packages/catalog",
        "/api/vendor/business/profile",
    }
)

# While awaiting confirmation the vendor may still complete their own
# business information; every other request waits for the admin decision.
# The trailing slash keeps `business-payments/...` out of the allowlist.
# Writes are the reason this prefix exists, so unlike the boot and
# reference paths it deliberately is not limited to safe methods.
BUSINESS_INFO_PATH_PREFIX = "/api/vendor/business/"

# Reference data the onboarding wizard reads. A pending vendor is expected
# to be filling their business in, and this is the platform list that
# step depends on — it is not business data, so a ban does not lift it.
BUSINESS_REFERENCE_PATHS = frozenset(
    {
        "/api/business/public/social-medias",
    }
)

CODE_BANNED = "business_banned"
CODE_CONFIRMATION_AWAIT = "business_confirmation_await"


def _deny(message, code):
    """The house error envelope as a real HTTP response.

    `core.responses.api_response` returns a DRF `Response`, which only
    renders inside a view, so the same shape is built directly here.
    """
    return JsonResponse(
        {
            "success": False,
            "message": message,
            "data": None,
            "errors": {"detail": message, "code": code},
        },
        status=403,
    )


def _is_read_allowed(request, paths):
    """A read the shell needs in order to explain the refusal."""
    return request.method in SAFE_METHODS and request.path in paths


class BusinessStatusMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        status_id = self._vendor_business_status_id(request)
        if status_id is None:
            return self.get_response(request)

        path = request.path

        if status_id == BusinessStatusEnum.BANNED.value:
            # A ban lifts only the boot reads: enough to render the notice
            # and keep the session coherent, nothing of the shop itself.
            if _is_read_allowed(request, BOOT_PATHS):
                return self.get_response(request)
            return _deny(_("Your business has been banned."), CODE_BANNED)

        if status_id == BusinessStatusEnum.CONFIRMATION_AWAIT.value:
            if (
                path.startswith(BUSINESS_INFO_PATH_PREFIX)
                or _is_read_allowed(request, BOOT_PATHS)
                or _is_read_allowed(request, BUSINESS_REFERENCE_PATHS)
            ):
                return self.get_response(request)
            return _deny(
                _("Your business is awaiting confirmation."),
                CODE_CONFIRMATION_AWAIT,
            )

        return self.get_response(request)

    def _vendor_business_status_id(self, request):
        """The caller's business status, or None when the gate does not apply.

        None covers every pass-through case: no bearer token, a token
        that does not verify (expired/foreign — DRF answers 401 itself),
        a non-vendor principal, and a vendor with no business yet (the
        registration write itself).
        """
        header = request.headers.get("Authorization", "")
        if not header.startswith(BEARER_PREFIX):
            return None

        try:
            token = AccessToken(header[len(BEARER_PREFIX):])
        except TokenError:
            return None

        if token.payload.get("user_type") != VENDOR_USER_TYPE:
            return None

        vendor_id = token.payload.get("user_id")
        if vendor_id is None:
            return None

        # Imported lazily: this module is loaded from settings before the
        # app registry is ready, when importing models would raise.
        from domains.business.models import BusinessProfile

        # Uncached on purpose: one indexed lookup on the vendor's unique
        # constraint is nothing, and an admin's ban must land on the very
        # next request — reads included, since this now gates them too.
        return (
            BusinessProfile.objects.filter(vendor_id=vendor_id)
            .values_list("status_id", flat=True)
            .first()
        )
