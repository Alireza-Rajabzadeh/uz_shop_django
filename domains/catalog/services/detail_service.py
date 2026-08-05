from django.db import IntegrityError, transaction
from django.utils.translation import gettext as _
from rapidfuzz import fuzz

from core.constants import TYPE_SELECT
from core.services.base import BaseService
from domains.catalog.models import CategoryDetail, CategoryDetailOption
from domains.catalog.models.category_detail_relation import CategoryDetailRelation


class DetailService(BaseService):
    model = CategoryDetail

    class ValidationError(Exception):
        def __init__(self, errors):
            self.errors = errors
            super().__init__(str(errors))

    @staticmethod
    def normalize_name(name):
        return " ".join(name.split())

    def _prepare_data(self, data, instance=None):
        name = self.normalize_name(data.get("name", instance.name if instance else ""))
        duplicates = self.model.objects.all()
        if instance:
            duplicates = duplicates.exclude(pk=instance.pk)
        if any(
            self.normalize_name(detail_name).casefold() == name.casefold()
            for detail_name in duplicates.values_list("name", flat=True)
        ):
            raise self.ValidationError(
                {"name": [_("A category detail with this name already exists.")]}
            )

        detail_type = data.get("type", instance.type if instance else None)
        options = data.get("options", instance.options if instance else "")
        if detail_type == TYPE_SELECT:
            normalized_options = [option.strip() for option in options.split(",") if option.strip()]
            if not normalized_options:
                raise self.ValidationError(
                    {"options": [_("Select details require at least one option.")]}
                )
            options = ",".join(normalized_options)
        else:
            options = ""

        return {**data, "name": name, "options": options}

    @transaction.atomic
    def create_category_detail(self, **data):
        data = self._prepare_data(data)
        try:
            detail = self._create(**data)
            self._sync_options(detail)
            return detail
        except IntegrityError as exc:
            raise self.ValidationError(
                {"name": [_("A category detail with this name already exists.")]}
            ) from exc

    @transaction.atomic
    def update_category_detail(self, instance, **data):
        data = self._prepare_data(data, instance)
        try:
            detail = self._update(instance, **data)
            self._sync_options(detail)
            return detail
        except IntegrityError as exc:
            raise self.ValidationError(
                {"name": [_("A category detail with this name already exists.")]}
            ) from exc

    @staticmethod
    def _sync_options(detail):
        names = [name.strip() for name in detail.options.split(",") if name.strip()]
        existing = {
            option.name.casefold(): option
            for option in detail.normalized_options.all()
        }
        retained_ids = []
        for position, name in enumerate(names):
            option = existing.get(name.casefold())
            if option is None:
                option = CategoryDetailOption.objects.create(
                    detail=detail,
                    name=name,
                    position=position,
                )
            elif option.name != name or option.position != position:
                option.name = name
                option.position = position
                option.save(update_fields=["name", "position"])
            retained_ids.append(option.id)
        detail.normalized_options.exclude(id__in=retained_ids).delete()

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

    def find_name_matches(self, name, exclude_id=None, limit=5, threshold=65):
        normalized_name = self.normalize_name(name)
        queryset = self.model.objects.all()
        if exclude_id:
            queryset = queryset.exclude(pk=exclude_id)

        matches = []
        exact_duplicate = False
        for detail in queryset:
            score = round(fuzz.WRatio(normalized_name.casefold(), detail.name.casefold()))
            exact = self.normalize_name(detail.name).casefold() == normalized_name.casefold()
            exact_duplicate = exact_duplicate or exact
            if exact or score >= threshold:
                matches.append((exact, score, detail))

        matches.sort(key=lambda match: (not match[0], -match[1], match[2].name.casefold()))
        return exact_duplicate, matches[:limit]

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
