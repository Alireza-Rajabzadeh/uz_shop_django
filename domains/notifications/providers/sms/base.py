from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class SMSSendResult:
    external_id: str


@dataclass(frozen=True)
class SMSDeliveryResult:
    status: str


@dataclass(frozen=True)
class SMSHealth:
    healthy: bool
    message: str = ""


@dataclass(frozen=True)
class SMSBalance:
    amount: Decimal | None
    currency: str = ""


class BaseSMSProvider(ABC):
    @abstractmethod
    def send(self, receiver, message):
        raise NotImplementedError

    @abstractmethod
    def get_delivery_status(self, external_id):
        raise NotImplementedError

    @abstractmethod
    def get_health(self):
        raise NotImplementedError

    @abstractmethod
    def get_balance(self):
        raise NotImplementedError
