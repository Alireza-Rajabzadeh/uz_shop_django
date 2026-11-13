from django.db import transaction

from core.management.seeders.base import BaseSeeder
from domains.order.enums import OrderActionEnum, OrderStatusEnum
from domains.order.models import OrderAction, OrderStatus, OrderStatusAction

ORDER_STATUS_METADATA = {
    OrderStatusEnum.PAID: (
        "paid",
        "پرداخت شده",
        "پرداخت سفارش با موفقیت انجام شده و مرحله پرداخت تکمیل شده است.",
    ),
    OrderStatusEnum.PAYMENT_PENDING: (
        "payment_pending",
        "در انتظار پرداخت",
        "سفارش ایجاد شده اما پرداخت آن هنوز توسط مشتری انجام نشده است.",
    ),
    OrderStatusEnum.PAYMENT_PROCESSING: (
        "payment_processing",
        "در حال پردازش پرداخت",
        "درخواست پرداخت ثبت شده و نتیجه نهایی تراکنش در حال بررسی یا پردازش است.",
    ),
    OrderStatusEnum.PAYMENT_FAILED: (
        "payment_failed",
        "پرداخت ناموفق",
        "عملیات پرداخت با خطا مواجه شده و مبلغ سفارش با موفقیت پرداخت نشده است.",
    ),
    OrderStatusEnum.PAYMENT_EXPIRED: (
        "payment_expired",
        "مهلت پرداخت منقضی شده",
        "مهلت تعیین‌شده برای پرداخت سفارش به پایان رسیده است.",
    ),
    OrderStatusEnum.PAYMENT_CANCELLED: (
        "payment_cancelled",
        "پرداخت لغو شده",
        "فرآیند پرداخت توسط مشتری، درگاه پرداخت یا سیستم لغو شده است.",
    ),
    OrderStatusEnum.PROCESSED: (
        "processed",
        "پردازش تکمیل شده",
        "تمامی مراحل پردازش و آماده‌سازی سفارش با موفقیت تکمیل شده است.",
    ),
    OrderStatusEnum.CONFIRMED: (
        "confirmed",
        "سفارش تأیید شده",
        "سفارش پس از پرداخت یا بررسی‌های لازم توسط سیستم تأیید شده است.",
    ),
    OrderStatusEnum.INVENTORY_RESERVED: (
        "inventory_reserved",
        "موجودی رزرو شده",
        "موجودی مورد نیاز برای اقلام سفارش با موفقیت برای این سفارش رزرو شده است.",
    ),
    OrderStatusEnum.PREPARING: (
        "preparing",
        "در حال آماده‌سازی",
        "اقلام سفارش در حال جمع‌آوری و آماده‌سازی برای بسته‌بندی هستند.",
    ),
    OrderStatusEnum.PACKED: (
        "packed",
        "بسته‌بندی شده",
        "تمامی اقلام سفارش آماده و بسته‌بندی شده‌اند.",
    ),
    OrderStatusEnum.READY_FOR_SHIPMENT: (
        "ready_for_shipment",
        "آماده ارسال",
        "سفارش آماده تحویل به شرکت حمل یا پیک است.",
    ),
    OrderStatusEnum.PROCESSING_FAILED: (
        "processing_failed",
        "خطا در پردازش سفارش",
        "پردازش سفارش به دلیل مشکل سیستمی، موجودی یا سایر محدودیت‌ها با موفقیت انجام نشده است.",
    ),
    OrderStatusEnum.DELIVERED: (
        "delivered",
        "تحویل شده",
        "سفارش با موفقیت به مشتری یا گیرنده تحویل داده شده و مرحله ارسال تکمیل شده است.",
    ),
    OrderStatusEnum.SHIPPED: (
        "shipped",
        "ارسال شده",
        "سفارش به شرکت حمل، پست یا پیک تحویل داده شده است.",
    ),
    OrderStatusEnum.IN_TRANSIT: (
        "in_transit",
        "در مسیر ارسال",
        "مرسوله در شبکه حمل‌ونقل قرار دارد و در مسیر مقصد است.",
    ),
    OrderStatusEnum.OUT_FOR_DELIVERY: (
        "out_for_delivery",
        "در حال تحویل",
        "مرسوله برای تحویل نهایی در اختیار پیک یا مأمور تحویل قرار گرفته است.",
    ),
    OrderStatusEnum.DELIVERY_FAILED: (
        "delivery_failed",
        "تحویل ناموفق",
        "تلاش برای تحویل سفارش ناموفق بوده و سفارش به مشتری تحویل داده نشده است.",
    ),
    OrderStatusEnum.DELIVERY_DELAYED: (
        "delivery_delayed",
        "تأخیر در ارسال",
        "تحویل سفارش نسبت به زمان پیش‌بینی‌شده با تأخیر مواجه شده است.",
    ),
    OrderStatusEnum.RETURNED_TO_SENDER: (
        "returned_to_sender",
        "بازگشت به فرستنده",
        "مرسوله به دلیل عدم امکان تحویل یا سایر مشکلات به انبار یا فرستنده بازگردانده شده است.",
    ),
    OrderStatusEnum.RETURNED: (
        "returned",
        "مرجوع شده",
        "فرآیند مرجوعی کالا به طور کامل انجام شده و مرحله بازگشت کالا تکمیل شده است.",
    ),
    OrderStatusEnum.RETURN_REQUESTED: (
        "return_requested",
        "درخواست مرجوعی",
        "مشتری درخواست مرجوع کردن یک یا چند قلم از سفارش را ثبت کرده است.",
    ),
    OrderStatusEnum.RETURN_REVIEWING: (
        "return_reviewing",
        "در حال بررسی مرجوعی",
        "درخواست مرجوعی مشتری در حال بررسی شرایط و قوانین بازگشت کالا است.",
    ),
    OrderStatusEnum.RETURN_APPROVED: (
        "return_approved",
        "مرجوعی تأیید شده",
        "درخواست مرجوعی توسط سیستم یا اپراتور تأیید شده است.",
    ),
    OrderStatusEnum.RETURN_REJECTED: (
        "return_rejected",
        "مرجوعی رد شده",
        "درخواست مرجوعی به دلیل عدم تطابق با شرایط بازگشت کالا رد شده است.",
    ),
    OrderStatusEnum.RETURN_SHIPPING: (
        "return_shipping",
        "در حال ارسال مرجوعی",
        "مشتری کالا را برای بازگشت به فروشگاه یا انبار ارسال کرده است.",
    ),
    OrderStatusEnum.RETURN_RECEIVED: (
        "return_received",
        "کالای مرجوعی دریافت شده",
        "کالای مرجوعی توسط انبار یا فروشگاه دریافت شده است.",
    ),
    OrderStatusEnum.RETURN_INSPECTION: (
        "return_inspection",
        "در حال بررسی کالای مرجوعی",
        "کالای بازگشتی در حال بررسی از نظر سلامت، وضعیت فیزیکی و شرایط مرجوعی است.",
    ),
    OrderStatusEnum.CANCELLED: (
        "cancelled",
        "لغو شده",
        "فرآیند لغو سفارش با موفقیت تکمیل شده و سفارش نهایی لغو شده است.",
    ),
    OrderStatusEnum.CANCELLATION_REQUESTED: (
        "cancellation_requested",
        "درخواست لغو",
        "مشتری یا اپراتور درخواست لغو سفارش را ثبت کرده است.",
    ),
    OrderStatusEnum.CANCELLATION_PROCESSING: (
        "cancellation_processing",
        "در حال لغو سفارش",
        "درخواست لغو پذیرفته شده و عملیات لازم برای لغو سفارش در حال انجام است.",
    ),
    OrderStatusEnum.CANCELLATION_REJECTED: (
        "cancellation_rejected",
        "درخواست لغو رد شده",
        "درخواست لغو سفارش به دلیل وضعیت سفارش یا قوانین سیستم قابل انجام نبوده است.",
    ),
    OrderStatusEnum.REFUNDED: (
        "refunded",
        "وجه بازپرداخت شده",
        "مبلغ قابل بازپرداخت سفارش با موفقیت به مشتری بازگردانده شده است.",
    ),
    OrderStatusEnum.REFUND_PENDING: (
        "refund_pending",
        "در انتظار بازپرداخت",
        "بازپرداخت تأیید شده اما عملیات انتقال وجه هنوز آغاز یا تکمیل نشده است.",
    ),
    OrderStatusEnum.REFUND_PROCESSING: (
        "refund_processing",
        "در حال بازپرداخت",
        "درخواست بازپرداخت به سیستم مالی یا درگاه پرداخت ارسال شده و در حال پردازش است.",
    ),
    OrderStatusEnum.REFUND_FAILED: (
        "refund_failed",
        "بازپرداخت ناموفق",
        "عملیات بازپرداخت مبلغ با خطا مواجه شده و نیاز به بررسی یا تلاش مجدد دارد.",
    ),
}

ORDER_STATUSES = {
    status_enum.value: meta for status_enum, meta in ORDER_STATUS_METADATA.items()
}

ORDER_ACTION_METADATA = {
    OrderActionEnum.CANCEL: ("cancel", "Cancel order", "لغو سفارش", True, True, OrderStatusEnum.CANCELLED.value),
    OrderActionEnum.CONFIRM: ("confirm", "Confirm order", "تأیید سفارش", True, False, OrderStatusEnum.CONFIRMED.value),
    OrderActionEnum.PREPARE: ("prepare", "Prepare order", "آماده‌سازی سفارش", True, False, OrderStatusEnum.PREPARING.value),
    OrderActionEnum.PACK: ("pack", "Pack order", "بسته‌بندی سفارش", True, False, OrderStatusEnum.PACKED.value),
    OrderActionEnum.SHIP: ("ship", "Ship order", "ارسال سفارش", True, False, OrderStatusEnum.SHIPPED.value),
    OrderActionEnum.DELIVER: ("deliver", "Deliver order", "تحویل سفارش", True, False, OrderStatusEnum.DELIVERED.value),
    OrderActionEnum.REQUEST_RETURN: ("request_return", "Request return", "درخواست مرجوعی", False, True, None),
    OrderActionEnum.APPROVE_RETURN: ("approve_return", "Approve return", "تأیید مرجوعی", True, False, OrderStatusEnum.RETURN_APPROVED.value),
    OrderActionEnum.REJECT_RETURN: ("reject_return", "Reject return", "رد مرجوعی", True, False, OrderStatusEnum.RETURN_REJECTED.value),
    OrderActionEnum.PROCESS_REFUND: ("process_refund", "Process refund", "پردازش بازپرداخت", True, False, OrderStatusEnum.REFUND_PROCESSING.value),
    OrderActionEnum.SUBMIT_PAYMENT: ("submit_payment", "Submit payment", "ثبت پرداخت", False, True, OrderStatusEnum.PAYMENT_PROCESSING.value),
    OrderActionEnum.APPROVE_PAYMENT: ("approve_payment", "Approve payment", "تأیید پرداخت", True, False, OrderStatusEnum.PAID.value),
    OrderActionEnum.REJECT_PAYMENT: ("reject_payment", "Reject payment", "رد پرداخت", True, False, OrderStatusEnum.PAYMENT_FAILED.value),
}

ORDER_ACTIONS = {
    action_enum.value: meta for action_enum, meta in ORDER_ACTION_METADATA.items()
}

ORDER_STATUS_ACTIONS = (
    (OrderStatusEnum.PAYMENT_PENDING.value, OrderActionEnum.CANCEL.value),
    (OrderStatusEnum.PAID.value, OrderActionEnum.CONFIRM.value),
    (OrderStatusEnum.CONFIRMED.value, OrderActionEnum.CANCEL.value),
    (OrderStatusEnum.CONFIRMED.value, OrderActionEnum.PREPARE.value),
    (OrderStatusEnum.PREPARING.value, OrderActionEnum.CANCEL.value),
    (OrderStatusEnum.PREPARING.value, OrderActionEnum.PACK.value),
    (OrderStatusEnum.PACKED.value, OrderActionEnum.CANCEL.value),
    (OrderStatusEnum.PACKED.value, OrderActionEnum.SHIP.value),
    (OrderStatusEnum.SHIPPED.value, OrderActionEnum.DELIVER.value),
    (OrderStatusEnum.DELIVERED.value, OrderActionEnum.REQUEST_RETURN.value),
    (OrderStatusEnum.RETURN_REVIEWING.value, OrderActionEnum.APPROVE_RETURN.value),
    (OrderStatusEnum.RETURN_REVIEWING.value, OrderActionEnum.REJECT_RETURN.value),
    (OrderStatusEnum.RETURN_APPROVED.value, OrderActionEnum.PROCESS_REFUND.value),
)


class OrderSeeder(BaseSeeder):
    @transaction.atomic
    def run(self):
        self._seed_statuses()
        self._seed_actions()
        self._seed_status_actions()
        self.sync_sequences(OrderStatus, OrderAction, OrderStatusAction)

    def _seed_statuses(self):
        status_ids = tuple(ORDER_STATUSES)
        for status in OrderStatus.objects.select_for_update().filter(id__in=status_ids):
            status.name = f"__order_status_seed_{status.id}__"
            status.save(update_fields=["name"])

        for status_enum, (name, fa_name, description) in ORDER_STATUS_METADATA.items():
            OrderStatus.objects.update_or_create(
                id=status_enum.value,
                defaults={
                    "name": name,
                    "fa_name": fa_name,
                    "description": description,
                },
            )

    def _seed_actions(self):
        action_ids = tuple(ORDER_ACTIONS)
        for action in OrderAction.objects.select_for_update().filter(id__in=action_ids):
            action.code = f"__order_action_seed_{action.id}__"
            action.save(update_fields=["code"])

        for action_enum, (code, name, fa_name, admin, customer, status_id) in ORDER_ACTION_METADATA.items():
            OrderAction.objects.update_or_create(
                id=action_enum.value,
                defaults={
                    "code": code,
                    "name": name,
                    "fa_name": fa_name,
                    "admin": admin,
                    "customer": customer,
                    "set_status_id": status_id,
                },
            )

    def _seed_status_actions(self):
        for status_id, action_id in ORDER_STATUS_ACTIONS:
            OrderStatusAction.objects.get_or_create(
                order_status_id=status_id,
                order_action_id=action_id,
            )
