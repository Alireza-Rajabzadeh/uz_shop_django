from abc import ABC, abstractmethod


class BaseOnlinePaymentProvider(ABC):
    @abstractmethod
    def create_payment(self, *, payment, callback_url):
        """Create a provider-side payment and return its redirect information."""

    @abstractmethod
    def verify_payment(self, *, payment, request_data):
        """Verify a provider callback and return provider verification data."""
