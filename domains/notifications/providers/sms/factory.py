from django.conf import settings

from .fake import FakeSMSProvider


class SMSProviderFactory:
    providers = {"fake-sms": FakeSMSProvider}

    class Error(Exception):
        pass

    @classmethod
    def create(cls, provider):
        if provider.code == "fake-sms" and not settings.NOTIFICATIONS_ALLOW_FAKE_SMS:
            raise cls.Error("The fake SMS provider is disabled.")
        provider_class = cls.providers.get(provider.code)
        if provider_class is None:
            raise cls.Error(f'Unsupported SMS provider "{provider.code}".')
        return provider_class()
