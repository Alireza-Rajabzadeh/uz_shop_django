from enum import Enum


class OrderActionEnum(Enum):
    CANCEL = 1
    CONFIRM = 2
    PREPARE = 3
    PACK = 4
    SHIP = 5
    DELIVER = 6
    REQUEST_RETURN = 7
    APPROVE_RETURN = 8
    REJECT_RETURN = 9
    PROCESS_REFUND = 10
    SUBMIT_PAYMENT = 11
    APPROVE_PAYMENT = 12
    REJECT_PAYMENT = 13
