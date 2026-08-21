from django.apps import AppConfig


class BusinessConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "domains.business"

    def ready(self):
        from . import signals  # noqa: F401
