from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q

from domains.catalog.models import (
    Category,
    CategoryDetail,
    CategoryDetailRelation,
    CategoryVariantAttribute,
    Product,
    ProductDetails,
    ProductFile,
    ProductVariants,
    ProductVariantSelection,
)
from domains.inventory.models import SerializedStock, WarehouseStock


class Command(BaseCommand):
    help = "Remove development test data (test categories, details, and products)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--yes",
            action="store_true",
            help="Skip the confirmation prompt.",
        )

    @staticmethod
    def _test_product_qs():
        return Product.objects.filter(
            Q(name__startswith="Test Product") | Q(name="test")
        )

    @staticmethod
    def _test_category_qs():
        return Category.objects.filter(id__lt=1001)

    @staticmethod
    def _test_detail_qs():
        return CategoryDetail.objects.filter(name__startswith="Test Detail")

    def handle(self, *args, **options):
        products = list(self._test_product_qs().values_list("id", "name"))
        categories = list(self._test_category_qs().values_list("id", "name"))
        details = list(self._test_detail_qs().values_list("id", "name"))

        product_ids = [pk for pk, _ in products]
        category_ids = [pk for pk, _ in categories]
        detail_ids = [pk for pk, _ in details]

        related = {
            "product details": ProductDetails.objects.filter(
                product_id__in=product_ids
            ).count(),
            "product files": ProductFile.objects.filter(
                product_id__in=product_ids
            ).count(),
            "serialized stock": SerializedStock.objects.filter(
                variant__product_id__in=product_ids
            ).count(),
            "warehouse stock": WarehouseStock.objects.filter(
                variant__product_id__in=product_ids
            ).count(),
            "product variants": ProductVariants.objects.filter(
                product_id__in=product_ids
            ).count(),
            "variant selections": ProductVariantSelection.objects.filter(
                variant__product_id__in=product_ids
            ).count(),
            "category detail relations": CategoryDetailRelation.objects.filter(
                category_id__in=category_ids
            ).count(),
            "category variant attribute assignments": (
                CategoryVariantAttribute.objects.filter(
                    category_id__in=category_ids
                ).count()
            ),
        }

        self.stdout.write("Items to delete:")
        self.stdout.write(f"  products: {len(product_ids)}")
        self.stdout.write(f"  categories: {len(category_ids)}")
        self.stdout.write(f"  details: {len(detail_ids)}")
        for label, count in related.items():
            self.stdout.write(f"  related {label}: {count}")

        if not (product_ids or category_ids or detail_ids):
            self.stdout.write(self.style.SUCCESS("Nothing to clean."))
            return

        if not options["yes"]:
            answer = input(
                "This permanently deletes the listed test data. Continue? [y/N] "
            )
            if answer.strip().lower() not in {"y", "yes"}:
                self.stdout.write(self.style.WARNING("Aborted."))
                return

        with transaction.atomic():
            ProductDetails.objects.filter(product_id__in=product_ids).delete()
            ProductFile.objects.filter(product_id__in=product_ids).delete()
            SerializedStock.objects.filter(
                variant__product_id__in=product_ids
            ).delete()
            WarehouseStock.objects.filter(
                variant__product_id__in=product_ids
            ).delete()
            ProductVariantSelection.objects.filter(
                variant__product_id__in=product_ids
            ).delete()
            ProductVariants.objects.filter(product_id__in=product_ids).delete()
            self._test_product_qs().delete()
            self._test_category_qs().delete()
            self._test_detail_qs().delete()

        self.stdout.write(
            self.style.SUCCESS(
                f"Removed {len(product_ids)} products, "
                f"{len(category_ids)} categories, and {len(detail_ids)} details."
            )
        )
