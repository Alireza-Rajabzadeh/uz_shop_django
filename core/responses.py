from rest_framework.response import Response


def api_response(success=True, message="", data=None, errors=None, status_code=200):
    return Response(
        {
            "success": success,
            "message": message,
            "data": data,
            "errors": errors,
        },
        status=status_code,
    )