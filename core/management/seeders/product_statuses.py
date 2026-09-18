from core.management.seeders.base import BaseSeeder
from domains.catalog.models import ProductStatus


class ProductStatusSeeder(BaseSeeder):
    def run(self):
        for name in (
            "active", "inactive", "pending", "preorder",
            "wait_for_admin_confirmation", "admin_rejected",
        ):
            status = ProductStatus.objects.filter(name__iexact=name).first()
            if status is None:
                ProductStatus.objects.create(name=name)
            elif status.name != name:
                status.name = name
                status.save(update_fields=["name"])
