from core.management.seeders.base import BaseSeeder
from domains.business_payments.models import BusinessPaymentStatus


class BusinessPaymentStatusSeeder(BaseSeeder):
    STATUSES = [
        ("pending", "در انتظار پرداخت"),
        ("successful", "پرداخت موفق"),
        ("failed", "پرداخت ناموفق"),
    ]

    def run(self):
        for name, title in self.STATUSES:
            BusinessPaymentStatus.objects.get_or_create(
                name=name,
                defaults={"title": title, "is_active": True},
            )
