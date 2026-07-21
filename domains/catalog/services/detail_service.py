from core.services.base import BaseService
from domains.catalog.models import CategoryDetail
from domains.catalog.models.category_detail_relation import CategoryDetailRelation


class DetailService(BaseService):
    model = CategoryDetail

    def assign_to_category(self, category, detail, value):
        return CategoryDetailRelation.objects.create(
            category=category,
            detail=detail,
            value=value,
        )

    def get_for_category(self, category):
        return CategoryDetailRelation.objects.filter(category=category).select_related("detail")

    def validate_value(self, detail, value):
        if detail.type == "select" and detail.options:
            options = [o.strip() for o in detail.options.split(",")]
            if value not in options:
                raise ValueError(f"'{value}' is not a valid option. Choices: {', '.join(options)}")
        return True
