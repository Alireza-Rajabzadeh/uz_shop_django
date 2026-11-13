from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"

    def ready(self):
        super().ready()
        try:
            import sys
            from django.core.management import get_commands
            from core.management.commands import seed, seed_fake

            # Support 'seed:fake' and 'seed:config' aliases in Django management dispatcher
            sys.modules["core.management.commands.seed:fake"] = seed_fake
            sys.modules["core.management.commands.seed:config"] = seed
            commands = get_commands()
            commands["seed:fake"] = "core"
            commands["seed:config"] = "core"
        except Exception:
            pass
