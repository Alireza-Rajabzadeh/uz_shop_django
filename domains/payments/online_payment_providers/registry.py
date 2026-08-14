from importlib import import_module

from .base import BaseOnlinePaymentProvider


def provider_class(code):
    try:
        module = import_module(f"domains.payments.online_payment_providers.{code}")
        provider = getattr(module, f"{code.title().replace('_', '')}Provider")
    except (ImportError, AttributeError, ValueError):
        return None
    if not isinstance(provider, type) or not issubclass(provider, BaseOnlinePaymentProvider):
        return None
    return provider


def provider_availability(code):
    if provider_class(code) is None:
        return False, "Online payment provider is not implemented."
    return True, None
