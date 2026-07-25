from django.db import transaction
from core.services.base import BaseService
from domains.catalog.models import Category
from domains.catalog.models.category_detail_relation import CategoryDetailRelation


class CategoryService(BaseService):
    model = Category

    def create_category(self, **data):
        return self._create(**data)

    def update_category(self, instance, **data):
        return self._update(instance, **data)

    def delete_category(self, instance):
        self._delete(instance)

    def get_category(self, id):
        return self._get(id)

    def search_categories(self, **filters):
        return self._list(**filters)

    def get_tree(self):
        return self.model.objects.filter(parent__isnull=True).prefetch_related("children")

    def get_with_details(self, id):
        return self.model.objects.prefetch_related(
            "categorydetailrelation_set__detail"
        ).get(id=id)

    @transaction.atomic
    def assign_multiple_detail_to_category(self, category, detail_data_list):
        existing_ids = set(
            CategoryDetailRelation.objects.filter(category=category)
            .values_list("detail_id", flat=True)
        )
        incoming_ids = {item["detail_id"] for item in detail_data_list}

        CategoryDetailRelation.objects.filter(
            category=category, detail_id__in=existing_ids - incoming_ids
        ).delete()

        to_add = []
        for item in detail_data_list:
            if item["detail_id"] not in existing_ids:
                to_add.append(
                    CategoryDetailRelation(
                        category=category,
                        detail_id=item["detail_id"],
                        value=item.get("value", ""),
                    )
                )
        if to_add:
            CategoryDetailRelation.objects.bulk_create(to_add)
