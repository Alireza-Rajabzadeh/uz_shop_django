import re

from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.db.models import Q
from django.utils.translation import gettext as _

from domains.catalog.models import VariantAttribute, VariantOption


class VariantAttributeService:
    class ValidationError(Exception):
        def __init__(self, errors):
            self.errors = errors
            super().__init__(str(errors))

    @staticmethod
    def normalize_name(name):
        return " ".join(name.split())

    @staticmethod
    def normalize_sku_code(code):
        code = code.strip().upper()
        if not re.fullmatch(r"[A-Z0-9]+", code):
            raise VariantAttributeService.ValidationError({
                "sku_code": [_('SKU code must contain only letters and numbers.')]
            })
        return code

    def list_attributes(self, search=None):
        queryset = VariantAttribute.objects.prefetch_related("options")
        if search:
            query = (
                Q(name__icontains=search)
                | Q(options__name__icontains=search)
                | Q(options__sku_code__icontains=search)
            )
            if search.strip().isdigit():
                query |= Q(id=int(search)) | Q(options__id=int(search))
            queryset = queryset.filter(query).distinct()
        return queryset.order_by("name", "id")

    def list_options(self, search=None, attribute_id=None):
        queryset = VariantOption.objects.select_related("attribute")
        if search:
            query = (
                Q(name__icontains=search)
                | Q(fa_name__icontains=search)
                | Q(sku_code__icontains=search)
                | Q(attribute__name__icontains=search)
            )
            if search.strip().isdigit():
                query |= Q(id=int(search)) | Q(attribute_id=int(search))
            queryset = queryset.filter(query)
        if attribute_id:
            queryset = queryset.filter(attribute_id=attribute_id)
        return queryset.order_by("attribute__name", "name", "id")

    def get_attribute(self, id):
        return VariantAttribute.objects.prefetch_related("options").get(pk=id)

    def get_option(self, id):
        return VariantOption.objects.select_related("attribute").get(pk=id)

    def delete_attribute(self, instance):
        try:
            instance.delete()
        except ProtectedError as exc:
            raise self.ValidationError({
                "attribute": [_('An attribute used by product variants cannot be deleted.')]
            }) from exc

    def delete_option(self, instance):
        try:
            instance.delete()
        except ProtectedError as exc:
            raise self.ValidationError({
                "option": [_('An option used by product variants cannot be deleted.')]
            }) from exc

    @transaction.atomic
    def create_attribute(self, *, name):
        name = self.normalize_name(name)
        try:
            with transaction.atomic():
                return VariantAttribute.objects.create(name=name)
        except IntegrityError as exc:
            raise self.ValidationError({
                "name": [_('A variant attribute with this name already exists.')]
            }) from exc

    @transaction.atomic
    def update_attribute(self, instance, *, name):
        instance.name = self.normalize_name(name)
        try:
            with transaction.atomic():
                instance.save(update_fields=["name"])
        except IntegrityError as exc:
            raise self.ValidationError({
                "name": [_('A variant attribute with this name already exists.')]
            }) from exc
        return instance

    @transaction.atomic
    def create_option(self, *, attribute, name, sku_code, fa_name=None, info=None):
        try:
            with transaction.atomic():
                return VariantOption.objects.create(
                    attribute=attribute,
                    name=self.normalize_name(name),
                    fa_name=self.normalize_name(fa_name) if fa_name else None,
                    info=self.normalize_name(info) if info else "",
                    sku_code=self.normalize_sku_code(sku_code),
                )
        except IntegrityError as exc:
            raise self.ValidationError({
                "option": [_('The option name or SKU code is already in use.')]
            }) from exc

    @transaction.atomic
    def update_option(self, instance, **data):
        instance = VariantOption.objects.select_for_update().get(pk=instance.pk)
        attribute = data.get("attribute", instance.attribute)
        if attribute != instance.attribute and instance.variant_selections.exists():
            raise self.ValidationError({
                "attribute": [_('An option used by variants cannot change attribute.')]
            })
        instance.attribute = attribute
        instance.name = self.normalize_name(data.get("name", instance.name))
        if data.get("fa_name") is not None:
            instance.fa_name = self.normalize_name(data["fa_name"]) if data["fa_name"] else None
        if data.get("info") is not None:
            instance.info = self.normalize_name(data["info"]) if data["info"] else ""
        old_code = instance.sku_code
        instance.sku_code = self.normalize_sku_code(
            data.get("sku_code", instance.sku_code)
        )
        try:
            with transaction.atomic():
                instance.save(update_fields=["attribute", "name", "fa_name", "info", "sku_code"])
                if instance.sku_code != old_code:
                    from domains.catalog.services.product_service import ProductService

                    ProductService().regenerate_variants_for_option(instance)
        except IntegrityError as exc:
            raise self.ValidationError({
                "option": [_('The option name, SKU code, or generated variant SKU conflicts.')]
            }) from exc
        return instance
