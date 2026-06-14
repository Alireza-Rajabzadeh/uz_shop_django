from seeders.base import BaseSeeder
from domains.catalog.models import Product
from domains.catalog.models.category import Category


class ProductSeeder(BaseSeeder):
    def run(self):
        category_model = Category.objects.first()

        Product.objects.get_or_create(
            name="Basic T-shirt",
            category=category_model,
        )