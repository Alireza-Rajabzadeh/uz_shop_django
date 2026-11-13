from enum import Enum


class PaymentMethodEnum(Enum):
    ONLINE = 1
    CARD_TO_CARD = 2
    DEPOSIT_TO_ACCOUNT = 3
    CREDIT = 4

    @property
    def code(self) -> str:
        return {
            PaymentMethodEnum.ONLINE: "online",
            PaymentMethodEnum.CARD_TO_CARD: "card_to_card",
            PaymentMethodEnum.DEPOSIT_TO_ACCOUNT: "deposit_to_account",
            PaymentMethodEnum.CREDIT: "credit",
        }[self]
