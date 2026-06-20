import traceback
from django.conf import settings
from rest_framework.views import exception_handler
from responses import api_response

def custom_exception_handler(exc, context):
    """
    Global DRF exception handler that:
    - Keeps consistent apiResponse format
    - Handles DRF validation/auth errors
    - Handles unexpected server errors
    - Adds stack trace in DEBUG mode
    """

    debug = getattr(settings, "DEBUG", False)

    # optional stack trace (only in development)
    trace = traceback.format_exc() if debug else None

    # let DRF handle known exceptions first
    response = exception_handler(exc, context)

    if response is not None:
        return api_response(
            success=False,
            message=_extract_drf_message(response),
            data=None,
            errors=response.data,
            status_code=response.status_code,
        )

    # fallback for unexpected errors (500)
    return api_response(
        success=False,
        message=str(exc),
        data=None,
        errors={
            "type": exc.__class__.__name__,
            "trace": trace,
        },
        status_code=500,
    )


def _extract_drf_message(response):
    """
    Extract a clean human-readable message from DRF error responses
    instead of generic 'Request failed'
    """

    data = response.data

    # case 1: list errors
    if isinstance(data, list):
        return data[0]

    # case 2: dict errors (most common)
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, list) and len(value) > 0:
                return value[0]
            return str(value)

    # fallback
    return "Request failed"