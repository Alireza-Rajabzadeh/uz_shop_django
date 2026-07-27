import random

from core.management.seeders.base import BaseSeeder
from core.constants import TYPE_NUMBER, TYPE_SELECT, TYPE_TEXT
from domains.catalog.models import (
    Category,
    CategoryDetail,
    CategoryDetailRelation,
    CategoryStatus,
)
from domains.catalog.enums.CategoryStatusEnum import CategoryStatusEnum


class CategorySeeder(BaseSeeder):
    def run(self):
        for status in CategoryStatusEnum:
            CategoryStatus.objects.update_or_create(
                id=status.value,
                defaults={"name": status.name.lower()},
            )

        # Temporary development dataset; replace when catalog fixtures are finalized.
        categories = []
        roots = []
        for index in range(1, 11):
            category, _ = Category.objects.update_or_create(
                name=f"Test Category {index:03d}",
                defaults={
                    "status_id": ((index - 1) % len(CategoryStatusEnum)) + 1,
                    "parent": None,
                },
            )
            roots.append(category)
            categories.append(category)

        for index in range(11, 101):
            category, _ = Category.objects.update_or_create(
                name=f"Test Category {index:03d}",
                defaults={
                    "status_id": ((index - 1) % len(CategoryStatusEnum)) + 1,
                    "parent": roots[(index - 11) % len(roots)],
                },
            )
            categories.append(category)

        details = []
        detail_types = (TYPE_TEXT, TYPE_NUMBER, TYPE_SELECT)
        for index in range(1, 101):
            detail_type = detail_types[(index - 1) % len(detail_types)]
            detail, _ = CategoryDetail.objects.update_or_create(
                name=f"Test Detail {index:03d}",
                defaults={
                    "type": detail_type,
                    "required": index % 4 == 0,
                    "options": "Option A,Option B,Option C" if detail_type == TYPE_SELECT else "",
                    "filterable": index % 5 != 0,
                },
            )
            details.append(detail)

        randomizer = random.Random(42)
        relations = []
        select_options = ("Option A", "Option B", "Option C")
        for category_index, category in enumerate(categories, start=1):
            assigned_details = randomizer.sample(details, randomizer.randint(5, 12))
            for detail in assigned_details:
                detail_index = int(detail.name.rsplit(" ", 1)[-1])
                if detail.type == TYPE_NUMBER:
                    value = str((category_index * detail_index) % 1000)
                elif detail.type == TYPE_SELECT:
                    value = select_options[(category_index + detail_index) % len(select_options)]
                else:
                    value = f"Test value {category_index:03d}-{detail_index:03d}"
                relations.append(
                    CategoryDetailRelation(
                        category=category,
                        detail=detail,
                        value=value,
                    )
                )

        CategoryDetailRelation.objects.filter(
            category__in=categories,
            detail__in=details,
        ).delete()
        CategoryDetailRelation.objects.bulk_create(relations, batch_size=500)
