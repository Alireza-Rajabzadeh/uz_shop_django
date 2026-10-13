from django.apps import AppConfig


class PackagesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "domains.packages"

    def ready(self):
        # Registers the package price-history receivers exactly once, the
        # same way `domains.catalog`, `domains.business`, `domains.content`,
        # and `domains.business_content` register theirs.
        from . import signals  # noqa: F401
