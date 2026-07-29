from django.db.models.functions import Lower, Trim

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
            attribute = VariantAttribute.objects.annotate(
                normalized_name=Lower(Trim("name"))
            ).filter(normalized_name=name.strip().lower()).first()
            if attribute is None:
                attribute = VariantAttribute.objects.create(name=name)
            elif attribute.name != name:
                attribute.name = name
                attribute.save(update_fields=["name"])
            attributes[name] = attribute
            for option_name, sku_code in options:
                option = VariantOption.objects.filter(sku_code__iexact=sku_code).first()
                if option is None:
                    VariantOption.objects.create(
                        attribute=attribute, name=option_name, sku_code=sku_code
                    )
                else:
                    option.attribute = attribute
                    option.name = option_name
                    option.sku_code = sku_code
                    option.save(update_fields=["attribute", "name", "sku_code"])

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
