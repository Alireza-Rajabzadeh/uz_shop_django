from django.utils.translation import gettext as _
from core.services.base import BaseService
from domains.catalog.models import CategoryDetail
from domains.catalog.models.category_detail_relation import CategoryDetailRelation


class DetailService(BaseService):
    model = CategoryDetail

    def create_category_detail(self, **data):
        return self._create(**data)

    def update_category_detail(self, instance, **data):
        return self._update(instance, **data)

    def delete_category_detail(self, instance):
        self._delete(instance)

    def get_category_detail(self, id):
        return self._get(id)

    def search_category_details(self, ordering=None, **filters):
        ordering_fields = {
            "id": "id",
            "name": "name",
            "type": "type",
            "required": "required",
            "filterable": "filterable",
        }
        queryset = self.model.objects.filter(**filters)
        descending = ordering and ordering.startswith("-")
        requested_field = ordering.lstrip("-") if ordering else "id"
        order_field = ordering_fields.get(requested_field, "id")
        return queryset.order_by(f"-{order_field}" if descending else order_field)

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
                raise ValueError(
                    _("'{value}' is not a valid option. Choices: {choices}").format(
                        value=value, choices=", ".join(options)
                    )
                )
        return True
