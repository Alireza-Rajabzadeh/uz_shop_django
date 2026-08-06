from django.db.models.functions import Lower, Trim

from core.management.seeders.base import BaseSeeder
from domains.catalog.models import (
    VariantAttribute,
    VariantOption,
)


class VariantAttributeSeeder(BaseSeeder):
    DATA = {
        "Color": [("Black", "مشکی", "BLK"), ("White", "سفید", "WHT"), ("Blue", "آبی", "BLU")],
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
            for option_name, fa_name, sku_code in options:
                option = VariantOption.objects.filter(sku_code__iexact=sku_code).first()
                if option is None:
                    VariantOption.objects.create(
                        attribute=attribute, name=option_name, fa_name=fa_name, sku_code=sku_code
                    )
                else:
                    option.attribute = attribute
                    option.name = option_name
                    option.fa_name = fa_name
                    option.sku_code = sku_code
                    option.save(update_fields=["attribute", "name", "fa_name", "sku_code"])
