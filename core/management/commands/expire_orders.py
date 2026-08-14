from django.core.management.base import BaseCommand

from domains.order.services import OrderService


class Command(BaseCommand):
    help = "Expire payment_pending orders whose reservation has passed"

    def handle(self, *args, **options):
        orders = OrderService().expire_orders()
        self.stdout.write(self.style.SUCCESS(f"Expired {len(orders)} orders"))
