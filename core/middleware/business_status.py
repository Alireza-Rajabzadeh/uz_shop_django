"""Project-wide write gate for the business lifecycle status.

Vendors are the only principals whose writes depend on an admin-managed
state: a registration that still awaits confirmation, and bans. Checking
it here — once, against the verified token's `user_type` claim — covers
every vendor write in the project, present and future, without a
per-view permission someone can forget to add.

The check fails open wherever it is not certain: safe methods pass
(reads stay open), a missing or undecodable bearer token passes (DRF
still owns authentication and answers 401 itself), non-vendor principals
pass by construction, and a vendor with no business yet passes so the
registration write can run.

Denials answer 403 in the house envelope with the codes
`business_banned` / `business_confirmation_await` — account state, not
entitlement, so deliberately distinct from the packages domain's 402.
"""

from django.http import JsonResponse
from django.utils.translation import gettext as _
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken

from domains.business.enums.BusinessStatusEnum import BusinessStatusEnum

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
BEARER_PREFIX = "Bearer "
VENDOR_USER_TYPE = "vendor"

# While awaiting confirmation the vendor may still complete their own
# business information; every other write waits for the admin decision.
# The trailing slash keeps `business-payments/...` out of the allowlist.
BUSINESS_INFO_PATH_PREFIX = "/api/vendor/business/"

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


class BusinessStatusMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method in SAFE_METHODS:
            return self.get_response(request)

        status_id = self._vendor_business_status_id(request)
        if status_id is None:
            return self.get_response(request)

        if status_id == BusinessStatusEnum.BANNED.value:
            return _deny(_("Your business has been banned."), CODE_BANNED)

        if (
            status_id == BusinessStatusEnum.CONFIRMATION_AWAIT.value
            and not request.path.startswith(BUSINESS_INFO_PATH_PREFIX)
        ):
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

        # Uncached on purpose: one indexed lookup per write is nothing,
        # and an admin's ban must land on the very next request.
        return (
            BusinessProfile.objects.filter(vendor_id=vendor_id)
            .values_list("status_id", flat=True)
            .first()
        )
