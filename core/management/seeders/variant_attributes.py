from django.db.models.functions import Lower, Trim

from core.management.seeders.base import BaseSeeder
from domains.catalog.models import (
    VariantAttribute,
    VariantOption,
)


class VariantAttributeSeeder(BaseSeeder):
    DATA = {
        "Color": [
            ("Black", "مشکی", "BLK", "#000000"),
            ("White", "سفید", "WHT", "#FFFFFF"),
            ("Blue", "آبی", "BLU", "#0000FF"),
        ],
        "Storage": [
            ("128 GB", "۱۲۸ گیگابایت", "128GB"),
            ("256 GB", "۲۵۶ گیگابایت", "256GB"),
            ("512 GB", "۵۱۲ گیگابایت", "512GB"),
        ],
        "Size": [("Small", "کوچک", "S"), ("Medium", "متوسط", "M"), ("Large", "بزرگ", "L")],
    }

    def run(self):
        for name, options in self.DATA.items():
            attribute = VariantAttribute.objects.annotate(
                normalized_name=Lower(Trim("name"))
            ).filter(normalized_name=name.strip().lower()).first()
            if attribute is None:
                attribute = VariantAttribute.objects.create(name=name)
            elif attribute.name != name:
                attribute.name = name
                attribute.save(update_fields=["name"])
            for option in options:
                option_name, fa_name, sku_code = option[0], option[1], option[2]
                info = option[3] if len(option) > 3 else ""
                existing = VariantOption.objects.filter(sku_code__iexact=sku_code).first()
                if existing is None:
                    VariantOption.objects.create(
                        attribute=attribute, name=option_name, fa_name=fa_name, sku_code=sku_code, info=info
                    )
                else:
                    existing.attribute = attribute
                    existing.name = option_name
                    existing.fa_name = fa_name
                    existing.info = info
                    existing.sku_code = sku_code
                    existing.save(update_fields=["attribute", "name", "fa_name", "info", "sku_code"])
