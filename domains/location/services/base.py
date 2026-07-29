import re

from django.db import IntegrityError
from django.db.models import BooleanField, Case, Count, Q, Value, When
from django.db.models.deletion import ProtectedError

from core.services.base import BaseService


class LocationValidationError(Exception):
    def __init__(self, errors):
        self.errors = errors
        super().__init__(str(errors))


def normalize_text(value):
    return re.sub(r"\s+", " ", value).strip()


class LocationService(BaseService):
    ordering_fields = {"id": "id", "name": "name", "fa_title": "fa_title"}

    def get(self, object_id):
        return self._get(object_id)

    def with_counts(self, object_id=None):
        queryset = self.annotate_counts(self.model.objects.all())
        return queryset.filter(pk=object_id) if object_id is not None else queryset

    def search(self, search=None, ordering=None, **filters):
        queryset = self.with_counts().select_related(*self.select_related)
        if search:
            query = Q()
            for field in self.search_fields:
                query |= Q(**{f"{field}__icontains": search})
            queryset = queryset.filter(query)
        queryset = self.apply_filters(queryset, **filters)
        direction = "-" if ordering and ordering.startswith("-") else ""
        requested = ordering.lstrip("-") if ordering else "id"
        order_field = self.ordering_fields.get(requested, "id")
        return queryset.order_by(f"{direction}{order_field}", "id")

    def apply_filters(self, queryset, **filters):
        return queryset

    def normalize_data(self, data):
        for field in ("name", "fa_title"):
            if field in data:
                data[field] = normalize_text(data[field])
        if not data.get("name", True):
            raise LocationValidationError({"name": ["This field may not be blank."]})
        return data

    def validate_duplicate(self, data, instance=None):
        filters = {field: data.get(field, getattr(instance, field, None)) for field in self.unique_scope}
        queryset = self.model.objects.filter(**{
            **{field: value for field, value in filters.items() if field != "name"},
            "name__iexact": filters["name"],
        })
        if instance:
            queryset = queryset.exclude(pk=instance.pk)
        if queryset.exists():
            raise LocationValidationError({"name": ["A location with this name already exists."]})

    def create(self, **data):
        data = self.normalize_data(data)
        self.validate_duplicate(data)
        try:
            return self.model.objects.create(**data)
        except IntegrityError as exc:
            raise LocationValidationError({"non_field_errors": ["This location already exists."]}) from exc

    def update(self, instance, **data):
        data = self.normalize_data(data)
        self.validate_duplicate(data, instance)
        for field, value in data.items():
            setattr(instance, field, value)
        try:
            instance.save()
        except IntegrityError as exc:
            raise LocationValidationError({"non_field_errors": ["This location already exists."]}) from exc
        return instance

    def delete(self, instance):
        blockers = self.delete_blockers(instance)
        if any(blockers.values()):
            raise LocationValidationError({
                "blockers": blockers,
                "detail": ["Delete dependent locations or references first."],
            })
        try:
            instance.delete()
        except ProtectedError as exc:
            raise LocationValidationError({
                "detail": ["This location is still referenced and cannot be deleted."]
            }) from exc

    @staticmethod
    def can_delete_case(*blocker_fields):
        return Case(
            When(**{field: 0 for field in blocker_fields}, then=Value(True)),
            default=Value(False), output_field=BooleanField(),
        )
