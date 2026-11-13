from enum import Enum


class BusinessPaymentMethodEnum(Enum):
    ONLINE = 1
    CARD_TO_CARD = 2
    DEPOSIT_TO_ACCOUNT = 3

    @property
    def code(self) -> str:
        return {
            BusinessPaymentMethodEnum.ONLINE: "online",
            BusinessPaymentMethodEnum.CARD_TO_CARD: "card_to_card",
            BusinessPaymentMethodEnum.DEPOSIT_TO_ACCOUNT: "deposit_to_account",
        }[self]
