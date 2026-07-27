from django.db import IntegrityError, transaction
from django.utils.translation import gettext as _
from rapidfuzz import fuzz
from core.services.base import BaseService
from domains.catalog.models import Category, CategoryStatus
from domains.catalog.models.category_detail_relation import CategoryDetailRelation


class CategoryService(BaseService):
    model = Category

    class ValidationError(Exception):
        def __init__(self, errors):
            self.errors = errors
            super().__init__(str(errors))

    @staticmethod
    def normalize_name(name):
        return " ".join(name.split())

    def _validate_category(self, name, parent=None, instance=None):
        normalized_name = self.normalize_name(name)
        duplicates = self.model.objects.all()
        if instance:
            duplicates = duplicates.exclude(pk=instance.pk)
        if any(
            self.normalize_name(category_name).casefold() == normalized_name.casefold()
            for category_name in duplicates.values_list("name", flat=True)
        ):
            raise self.ValidationError(
                {"name": [_("A category with this name already exists.")]}
            )

        if instance and parent:
            ancestor = parent
            while ancestor:
                if ancestor.pk == instance.pk:
                    raise self.ValidationError(
                        {"parent": [_("A category cannot use itself or a descendant as its parent.")]}
                    )
                ancestor = ancestor.parent

        return normalized_name

    @transaction.atomic
    def create_category(self, **data):
        data["name"] = self._validate_category(data["name"], data.get("parent"))
        try:
            return self._create(**data)
        except IntegrityError as exc:
            raise self.ValidationError(
                {"name": [_("A category with this name already exists.")]}
            ) from exc

    @transaction.atomic
    def update_category(self, instance, **data):
        name = data.get("name", instance.name)
        parent = data.get("parent", instance.parent)
        data["name"] = self._validate_category(name, parent, instance)
        try:
            return self._update(instance, **data)
        except IntegrityError as exc:
            raise self.ValidationError(
                {"name": [_("A category with this name already exists.")]}
            ) from exc

    def delete_category(self, instance):
        self._delete(instance)

    def get_category(self, id):
        return self._get(id)

    def search_categories(self, ordering=None, **filters):
        ordering_fields = {
            "id": "id",
            "name": "name",
            "parent_name": "parent__name",
            "status_name": "status__name",
        }
        queryset = self.model.objects.filter(**filters).select_related("parent", "status")
        descending = ordering and ordering.startswith("-")
        requested_field = ordering.lstrip("-") if ordering else "id"
        order_field = ordering_fields.get(requested_field, "id")
        return queryset.order_by(f"-{order_field}" if descending else order_field)

    def list_statuses(self):
        return CategoryStatus.objects.order_by("id")

    def get_tree(self):
        return self.model.objects.filter(parent__isnull=True).prefetch_related("children")

    def find_name_matches(self, name, exclude_id=None, limit=5, threshold=65):
        normalized_name = self.normalize_name(name)
        queryset = self.model.objects.select_related("parent", "status")
        if exclude_id:
            queryset = queryset.exclude(pk=exclude_id)

        matches = []
        exact_duplicate = False
        for category in queryset:
            score = round(fuzz.WRatio(normalized_name.casefold(), category.name.casefold()))
            exact = self.normalize_name(category.name).casefold() == normalized_name.casefold()
            exact_duplicate = exact_duplicate or exact
            if exact or score >= threshold:
                matches.append((exact, score, category))

        matches.sort(key=lambda match: (not match[0], -match[1], match[2].name.casefold()))
        return exact_duplicate, matches[:limit]

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
