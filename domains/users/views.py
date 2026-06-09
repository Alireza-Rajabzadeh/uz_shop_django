from django.utils import translation
from django.utils.translation import gettext as _
from rest_framework.decorators import api_view
from core.responses import api_response
from rest_framework.exceptions import ValidationError,PermissionDenied

@api_view(["GET"])
def test_api(request):
    return api_response(
        message=_("Hello World"),
        data={
            "domain": "users",
             "language": translation.get_language(),
            "status": "ok"
        }
    )


@api_view(["GET"])
def crash_test(request):
      raise PermissionDenied(_("You are not authorized to perform this action"))

