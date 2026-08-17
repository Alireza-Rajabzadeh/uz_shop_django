import os

from celery import Celery
from kombu.transport.redis import GlobalKeyPrefixMixin

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

# Kombu 5.5 does not prefix EXISTS during passive queue checks.
if "EXISTS" not in GlobalKeyPrefixMixin.PREFIXED_SIMPLE_COMMANDS:
    GlobalKeyPrefixMixin.PREFIXED_SIMPLE_COMMANDS.append("EXISTS")

app = Celery("uzshop")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
