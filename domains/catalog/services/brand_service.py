from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.utils.translation import gettext as _

from core.services.base import BaseService
from domains.catalog.models import Brand


class BrandService(BaseService):
    model = Brand

    class ValidationError(Exception):
        def __init__(self, errors):
            self.errors = errors
            super().__init__(str(errors))

    @staticmethod
    def normalize_name(name):
        return " ".join(name.split())

    def _validate_name(self, name, instance=None):
        normalized_name = self.normalize_name(name)
        duplicates = self.model.objects.all()
        if instance:
            duplicates = duplicates.exclude(pk=instance.pk)
        if any(
            self.normalize_name(brand_name).casefold() == normalized_name.casefold()
            for brand_name in duplicates.values_list("name", flat=True)
        ):
            raise self.ValidationError(
                {"name": [_("A brand with this name already exists.")]}
            )
        return normalized_name

    @transaction.atomic
    def create_brand(self, *, name, fa_name=None):
        name = self._validate_name(name)
        try:
            return self._create(name=name, fa_name=fa_name)
        except IntegrityError as exc:
            raise self.ValidationError(
                {"name": [_("A brand with this name already exists.")]}
            ) from exc

    @transaction.atomic
    def update_brand(self, instance, *, name, fa_name=None):
        name = self._validate_name(name, instance)
        instance.name = name
        instance.fa_name = fa_name
        try:
            with transaction.atomic():
                instance.save(update_fields=["name", "fa_name"])
        except IntegrityError as exc:
            raise self.ValidationError(
                {"name": [_("A brand with this name already exists.")]}
            ) from exc
        return instance

    def delete_brand(self, instance):
        try:
            instance.delete()
        except ProtectedError as exc:
            raise self.ValidationError({
                "brand": [_("A brand used by products cannot be deleted.")]
            }) from exc

    def get_brand(self, id):
        return self._get(id)

    def search_brands(self, ordering=None, **filters):
        ordering_map = {
            "id": "id",
            "name": "name",
            "fa_name": "fa_name",
        }
        queryset = self.model.objects.filter(**filters)
        descending = ordering and ordering.startswith("-")
        requested = ordering.lstrip("-") if ordering else "name"
        field = ordering_map.get(requested, "name")
        return queryset.order_by(f"-{field}" if descending else field, "id")

    def find_name_matches(self, name, exclude_id=None, limit=5, threshold=70):
        from rapidfuzz import fuzz

        normalized_name = self.normalize_name(name)
        queryset = self.model.objects.all()
        if exclude_id:
            queryset = queryset.exclude(pk=exclude_id)

        matches = []
        exact_duplicate = False
        for brand in queryset:
            score = round(fuzz.WRatio(normalized_name.casefold(), brand.name.casefold()))
            exact = self.normalize_name(brand.name).casefold() == normalized_name.casefold()
            exact_duplicate = exact_duplicate or exact
            if exact or score >= threshold:
                matches.append((exact, score, brand))

        matches.sort(key=lambda match: (not match[0], -match[1], match[2].name.casefold()))
        return exact_duplicate, matches[:limit]