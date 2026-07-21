from core.services.base import BaseService
from domains.catalog.models import Category


class CategoryService(BaseService):
    model = Category

    def get_tree(self):
        return self.model.objects.filter(parent__isnull=True).prefetch_related("children")

    def get_with_details(self, id):
        return self.model.objects.prefetch_related(
            "categorydetailrelation_set__detail"
        ).get(id=id)
