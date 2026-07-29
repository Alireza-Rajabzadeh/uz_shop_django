from django.db import IntegrityError, transaction
from django.utils import timezone

from domains.catalog.models import Product, ProductFile
from domains.files.models import File


class ProductFileService:
    class ValidationError(Exception):
        def __init__(self, errors):
            self.errors = errors
            super().__init__(str(errors))

    @staticmethod
    def list_for_product(product):
        return ProductFile.objects.filter(product=product).select_related(
            "file", "file__status"
        ).order_by("position", "id")

    @staticmethod
    def get_for_product(product, relation_id):
        return ProductFile.objects.filter(
            product=product, id=relation_id
        ).select_related("file", "file__status").first()

    @staticmethod
    def _validate_file(file):
        if file.status.name != "available" or file.deleted_at is not None:
            raise ProductFileService.ValidationError(
                {"file": "Only available files can be attached to products."}
            )

    @staticmethod
    def _validate_role(file, role, is_primary=False):
        expected_type = {
            ProductFile.Role.GALLERY: "image",
            ProductFile.Role.THUMBNAIL: "image",
            ProductFile.Role.VIDEO: "video",
            ProductFile.Role.DOCUMENT: "document",
        }[role]
        if file.file_type != expected_type:
            raise ProductFileService.ValidationError(
                {"role": f"The {role} role requires a {expected_type} file."}
            )
        if is_primary and file.file_type != "image":
            raise ProductFileService.ValidationError(
                {"is_primary": "Only images can be primary product media."}
            )

    @transaction.atomic
    def attach(self, product, file, **data):
        file = File.objects.select_for_update(of=("self",)).select_related(
            "status"
        ).get(pk=file.pk)
        product = Product.objects.select_for_update().get(pk=product.pk)
        self._validate_file(file)
        self._validate_role(file, data["role"], data.get("is_primary", False))
        if ProductFile.objects.filter(product=product, file=file).exists():
            raise self.ValidationError(
                {"file": "This file is already attached to the product."}
            )
        if data.get("is_primary"):
            ProductFile.objects.filter(
                product=product, is_primary=True
            ).update(is_primary=False)
        try:
            return ProductFile.objects.create(product=product, file=file, **data)
        except IntegrityError as exc:
            raise self.ValidationError(
                {"file": "This file is already attached to the product."}
            ) from exc

    @transaction.atomic
    def update(self, relation, **data):
        Product.objects.select_for_update().get(pk=relation.product_id)
        relation = ProductFile.objects.select_for_update(of=("self",)).select_related(
            "file", "file__status"
        ).get(pk=relation.pk)
        self._validate_role(
            relation.file,
            data.get("role", relation.role),
            data.get("is_primary", relation.is_primary),
        )
        if data.get("is_primary"):
            ProductFile.objects.filter(
                product=relation.product,
                is_primary=True,
            ).exclude(pk=relation.pk).update(is_primary=False)
        for field, value in data.items():
            setattr(relation, field, value)
        relation.save(update_fields=[*data.keys(), "updated_at"])
        return relation

    @staticmethod
    def delete(relation):
        relation.delete()

    @transaction.atomic
    def reorder(self, product, relation_ids):
        Product.objects.select_for_update().get(pk=product.pk)
        relations = list(
            ProductFile.objects.select_for_update(of=("self",))
            .filter(product=product)
            .order_by("position", "id")
        )
        existing_ids = {relation.id for relation in relations}
        if len(relation_ids) != len(set(relation_ids)) or set(relation_ids) != existing_ids:
            raise self.ValidationError(
                {"files": "Provide every product file exactly once."}
            )
        by_id = {relation.id: relation for relation in relations}
        ordered = [by_id[relation_id] for relation_id in relation_ids]
        updated_at = timezone.now()
        for position, relation in enumerate(ordered):
            relation.position = position
            relation.updated_at = updated_at
        ProductFile.objects.bulk_update(ordered, ["position", "updated_at"])
        return self.list_for_product(product)
