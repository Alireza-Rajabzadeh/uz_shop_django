from django.utils import translation

class HeaderLanguageMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):

        lang = request.headers.get("X-Language", "fa")

        if lang not in ["fa", "en", "tr"]:
            lang = "fa"

        translation.activate(lang)
        request.LANGUAGE_CODE = lang

        return self.get_response(request)