from core.management.seeders.base import BaseSeeder
from domains.catalog.models import (
    Category,
    CategoryVariantAttribute,
    VariantAttribute,
    VariantOption,
)


class VariantAttributeSeeder(BaseSeeder):
    DATA = {
        "Color": [("Black", "BLK"), ("White", "WHT"), ("Blue", "BLU")],
        "Storage": [("128 GB", "128GB"), ("256 GB", "256GB"), ("512 GB", "512GB")],
        "Size": [("Small", "S"), ("Medium", "M"), ("Large", "L")],
    }

    def run(self):
        attributes = {}
        for name, options in self.DATA.items():
            attribute, _ = VariantAttribute.objects.update_or_create(name=name)
            attributes[name] = attribute
            for option_name, sku_code in options:
                VariantOption.objects.update_or_create(
                    sku_code=sku_code,
                    defaults={"attribute": attribute, "name": option_name},
                )

        categories = list(Category.objects.filter(
            name__startswith="Test Category"
        ).order_by("id"))
        for index, category in enumerate(categories):
            suggested = [attributes["Color"]]
            if index % 2 == 0:
                suggested.append(attributes["Storage"])
            if index % 3 == 0:
                suggested.append(attributes["Size"])
            for attribute in suggested:
                CategoryVariantAttribute.objects.get_or_create(
                    category=category, attribute=attribute
                )
