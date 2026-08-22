from django.db import transaction

from core.management.seeders.base import BaseSeeder
from domains.order.models import OrderAction, OrderStatus, OrderStatusAction


ORDER_STATUSES = {
    100: (
        "paid",
        "پرداخت شده",
        "پرداخت سفارش با موفقیت انجام شده و مرحله پرداخت تکمیل شده است.",
    ),
    110: (
        "payment_pending",
        "در انتظار پرداخت",
        "سفارش ایجاد شده اما پرداخت آن هنوز توسط مشتری انجام نشده است.",
    ),
    120: (
        "payment_processing",
        "در حال پردازش پرداخت",
        "درخواست پرداخت ثبت شده و نتیجه نهایی تراکنش در حال بررسی یا پردازش است.",
    ),
    130: (
        "payment_failed",
        "پرداخت ناموفق",
        "عملیات پرداخت با خطا مواجه شده و مبلغ سفارش با موفقیت پرداخت نشده است.",
    ),
    140: (
        "payment_expired",
        "مهلت پرداخت منقضی شده",
        "مهلت تعیین‌شده برای پرداخت سفارش به پایان رسیده است.",
    ),
    150: (
        "payment_cancelled",
        "پرداخت لغو شده",
        "فرآیند پرداخت توسط مشتری، درگاه پرداخت یا سیستم لغو شده است.",
    ),
    200: (
        "processed",
        "پردازش تکمیل شده",
        "تمامی مراحل پردازش و آماده‌سازی سفارش با موفقیت تکمیل شده است.",
    ),
    210: (
        "confirmed",
        "سفارش تأیید شده",
        "سفارش پس از پرداخت یا بررسی‌های لازم توسط سیستم تأیید شده است.",
    ),
    220: (
        "inventory_reserved",
        "موجودی رزرو شده",
        "موجودی مورد نیاز برای اقلام سفارش با موفقیت برای این سفارش رزرو شده است.",
    ),
    230: (
        "preparing",
        "در حال آماده‌سازی",
        "اقلام سفارش در حال جمع‌آوری و آماده‌سازی برای بسته‌بندی هستند.",
    ),
    240: (
        "packed",
        "بسته‌بندی شده",
        "تمامی اقلام سفارش آماده و بسته‌بندی شده‌اند.",
    ),
    250: (
        "ready_for_shipment",
        "آماده ارسال",
        "سفارش آماده تحویل به شرکت حمل یا پیک است.",
    ),
    260: (
        "processing_failed",
        "خطا در پردازش سفارش",
        "پردازش سفارش به دلیل مشکل سیستمی، موجودی یا سایر محدودیت‌ها با موفقیت انجام نشده است.",
    ),
    300: (
        "delivered",
        "تحویل شده",
        "سفارش با موفقیت به مشتری یا گیرنده تحویل داده شده و مرحله ارسال تکمیل شده است.",
    ),
    310: (
        "shipped",
        "ارسال شده",
        "سفارش به شرکت حمل، پست یا پیک تحویل داده شده است.",
    ),
    320: (
        "in_transit",
        "در مسیر ارسال",
        "مرسوله در شبکه حمل‌ونقل قرار دارد و در مسیر مقصد است.",
    ),
    330: (
        "out_for_delivery",
        "در حال تحویل",
        "مرسوله برای تحویل نهایی در اختیار پیک یا مأمور تحویل قرار گرفته است.",
    ),
    340: (
        "delivery_failed",
        "تحویل ناموفق",
        "تلاش برای تحویل سفارش ناموفق بوده و سفارش به مشتری تحویل داده نشده است.",
    ),
    350: (
        "delivery_delayed",
        "تأخیر در ارسال",
        "تحویل سفارش نسبت به زمان پیش‌بینی‌شده با تأخیر مواجه شده است.",
    ),
    360: (
        "returned_to_sender",
        "بازگشت به فرستنده",
        "مرسوله به دلیل عدم امکان تحویل یا سایر مشکلات به انبار یا فرستنده بازگردانده شده است.",
    ),
    400: (
        "returned",
        "مرجوع شده",
        "فرآیند مرجوعی کالا به طور کامل انجام شده و مرحله بازگشت کالا تکمیل شده است.",
    ),
    410: (
        "return_requested",
        "درخواست مرجوعی",
        "مشتری درخواست مرجوع کردن یک یا چند قلم از سفارش را ثبت کرده است.",
    ),
    420: (
        "return_reviewing",
        "در حال بررسی مرجوعی",
        "درخواست مرجوعی مشتری در حال بررسی شرایط و قوانین بازگشت کالا است.",
    ),
    430: (
        "return_approved",
        "مرجوعی تأیید شده",
        "درخواست مرجوعی توسط سیستم یا اپراتور تأیید شده است.",
    ),
    440: (
        "return_rejected",
        "مرجوعی رد شده",
        "درخواست مرجوعی به دلیل عدم تطابق با شرایط بازگشت کالا رد شده است.",
    ),
    450: (
        "return_shipping",
        "در حال ارسال مرجوعی",
        "مشتری کالا را برای بازگشت به فروشگاه یا انبار ارسال کرده است.",
    ),
    460: (
        "return_received",
        "کالای مرجوعی دریافت شده",
        "کالای مرجوعی توسط انبار یا فروشگاه دریافت شده است.",
    ),
    470: (
        "return_inspection",
        "در حال بررسی کالای مرجوعی",
        "کالای بازگشتی در حال بررسی از نظر سلامت، وضعیت فیزیکی و شرایط مرجوعی است.",
    ),
    500: (
        "cancelled",
        "لغو شده",
        "فرآیند لغو سفارش با موفقیت تکمیل شده و سفارش نهایی لغو شده است.",
    ),
    510: (
        "cancellation_requested",
        "درخواست لغو",
        "مشتری یا اپراتور درخواست لغو سفارش را ثبت کرده است.",
    ),
    520: (
        "cancellation_processing",
        "در حال لغو سفارش",
        "درخواست لغو پذیرفته شده و عملیات لازم برای لغو سفارش در حال انجام است.",
    ),
    530: (
        "cancellation_rejected",
        "درخواست لغو رد شده",
        "درخواست لغو سفارش به دلیل وضعیت سفارش یا قوانین سیستم قابل انجام نبوده است.",
    ),
    600: (
        "refunded",
        "وجه بازپرداخت شده",
        "مبلغ قابل بازپرداخت سفارش با موفقیت به مشتری بازگردانده شده است.",
    ),
    610: (
        "refund_pending",
        "در انتظار بازپرداخت",
        "بازپرداخت تأیید شده اما عملیات انتقال وجه هنوز آغاز یا تکمیل نشده است.",
    ),
    620: (
        "refund_processing",
        "در حال بازپرداخت",
        "درخواست بازپرداخت به سیستم مالی یا درگاه پرداخت ارسال شده و در حال پردازش است.",
    ),
    630: (
        "refund_failed",
        "بازپرداخت ناموفق",
        "عملیات بازپرداخت مبلغ با خطا مواجه شده و نیاز به بررسی یا تلاش مجدد دارد.",
    ),
}

ORDER_ACTIONS = {
    1: ("cancel", "Cancel order", "لغو سفارش", True, True, 500),
    2: ("confirm", "Confirm order", "تأیید سفارش", True, False, 210),
    3: ("prepare", "Prepare order", "آماده‌سازی سفارش", True, False, 230),
    4: ("pack", "Pack order", "بسته‌بندی سفارش", True, False, 240),
    5: ("ship", "Ship order", "ارسال سفارش", True, False, 310),
    6: ("deliver", "Deliver order", "تحویل سفارش", True, False, 300),
    7: ("request_return", "Request return", "درخواست مرجوعی", False, True, None),
    8: ("approve_return", "Approve return", "تأیید مرجوعی", True, False, 430),
    9: ("reject_return", "Reject return", "رد مرجوعی", True, False, 440),
    10: ("process_refund", "Process refund", "پردازش بازپرداخت", True, False, 620),
    11: ("submit_payment", "Submit payment", "ثبت پرداخت", False, True, 120),
    12: ("approve_payment", "Approve payment", "تأیید پرداخت", True, False, 100),
    13: ("reject_payment", "Reject payment", "رد پرداخت", True, False, 130),
}

ORDER_STATUS_ACTIONS = (
    (110, 1),
    (100, 2),
    (210, 1),
    (210, 3),
    (230, 1),
    (230, 4),
    (240, 1),
    (240, 5),
    (310, 6),
    (300, 7),
    (420, 8),
    (420, 9),
    (430, 10),
)


class OrderSeeder(BaseSeeder):
    @transaction.atomic
    def run(self):
        self._seed_statuses()
        self._seed_actions()
        self._seed_status_actions()

    def _seed_statuses(self):
        status_ids = tuple(ORDER_STATUSES)
        # Free unique names before swapping canonical records between permanent IDs.
        for status in OrderStatus.objects.select_for_update().filter(id__in=status_ids):
            status.name = f"__order_status_seed_{status.id}__"
            status.save(update_fields=["name"])

        for status_id, (name, fa_name, description) in ORDER_STATUSES.items():
            OrderStatus.objects.update_or_create(
                id=status_id,
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

        for action_id, (code, name, fa_name, admin, customer, status_id) in ORDER_ACTIONS.items():
            OrderAction.objects.update_or_create(
                id=action_id,
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
