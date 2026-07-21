from core.services.base import BaseService
from domains.catalog.models import Product
from domains.catalog.models.product_details import ProductDetails


class ProductService(BaseService):
    model = Product

    def list_by_category(self, category_id):
        return self.model.objects.filter(category_id=category_id)

    def create_with_details(self, product_data, details_data=None):
        product = self.create(**product_data)
        if details_data:
            for detail in details_data:
                ProductDetails.objects.create(product=product, **detail)
        return product
