import traceback
from django.conf import settings
from rest_framework.views import exception_handler
from .responses import api_response


def custom_exception_handler(exc, context):
    debug = settings.DEBUG

    response = exception_handler(exc, context)

    if response is not None:
        errors = response.data

        if debug:
            errors = {
                "details": response.data,
                "exception": exc.__class__.__name__,
                "trace": traceback.format_exc(),
            }

        return api_response(
            success=False,
            message=_extract_drf_message(response),
            data=None,
            errors=errors,
            status_code=response.status_code,
        )

    errors = {
        "type": exc.__class__.__name__,
    }

    if debug:
        errors.update({
            "message": str(exc),
            "trace": traceback.format_exc(),
        })

    return api_response(
        success=False,
        message="Internal server error" if not debug else str(exc),
        data=None,
        errors=errors,
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