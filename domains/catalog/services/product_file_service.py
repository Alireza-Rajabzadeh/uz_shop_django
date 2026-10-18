from django.db import IntegrityError, transaction
from django.utils import timezone

from domains.catalog.models import Product, ProductFile, VendorProduct, VendorProductFile
from domains.files.models import File


class ProductFileService:
    """CRUD and validation for product-media relations.

    The catalog and the vendor submission tables carry the same relation shape
    for the same rule — only available files, the right role for the file
    type, at most one primary — so the rule lives here once and is pointed at
    a table by three class attributes rather than restated per table.
    """

    product_model = Product
    relation_model = ProductFile
    # Foreign key from the relation back to the row it hangs off. Differs
    # between the two tables (`product` vs `vendor_product`).
    product_field = "product"

    class ValidationError(Exception):
        def __init__(self, errors):
            self.errors = errors
            super().__init__(str(errors))

    @classmethod
    def _relations(cls, product):
        return cls.relation_model.objects.filter(**{cls.product_field: product})

    @classmethod
    def list_for_product(cls, product):
        return cls._relations(product).select_related(
            "file", "file__status"
        ).order_by("position", "id")

    @classmethod
    def get_for_product(cls, product, relation_id):
        return cls._relations(product).filter(id=relation_id).select_related(
            "file", "file__status"
        ).first()

    @classmethod
    def _validate_file(cls, file):
        if file.status.name != "available" or file.deleted_at is not None:
            raise cls.ValidationError(
                {"file": "Only available files can be attached to products."}
            )

    @classmethod
    def _validate_role(cls, file, role, is_primary=False):
        expected_type = {
            cls.relation_model.Role.GALLERY: "image",
            cls.relation_model.Role.THUMBNAIL: "image",
            cls.relation_model.Role.VIDEO: "video",
            cls.relation_model.Role.DOCUMENT: "document",
        }[role]
        if file.file_type != expected_type:
            raise cls.ValidationError(
                {"role": f"The {role} role requires a {expected_type} file."}
            )
        if is_primary and file.file_type != "image":
            raise cls.ValidationError(
                {"is_primary": "Only images can be primary product media."}
            )

    @transaction.atomic
    def attach(self, product, file, **data):
        file = File.objects.select_for_update(of=("self",)).select_related(
            "status"
        ).get(pk=file.pk)
        product = self.product_model.objects.select_for_update().get(pk=product.pk)
        self._validate_file(file)
        self._validate_role(file, data["role"], data.get("is_primary", False))
        if self._relations(product).filter(file=file).exists():
            raise self.ValidationError(
                {"file": "This file is already attached to the product."}
            )
        if data.get("is_primary"):
            self._relations(product).filter(
                is_primary=True
            ).update(is_primary=False)
        try:
            payload = {self.product_field: product, "file": file, **data}
            return self.relation_model.objects.create(**payload)
        except IntegrityError as exc:
            raise self.ValidationError(
                {"file": "This file is already attached to the product."}
            ) from exc

    @transaction.atomic
    def update(self, relation, **data):
        self.product_model.objects.select_for_update().get(
            pk=getattr(relation, f"{self.product_field}_id")
        )
        relation = self.relation_model.objects.select_for_update(of=("self",)).select_related(
            "file", "file__status"
        ).get(pk=relation.pk)
        self._validate_role(
            relation.file,
            data.get("role", relation.role),
            data.get("is_primary", relation.is_primary),
        )
        if data.get("is_primary"):
            self._relations(getattr(relation, self.product_field)).filter(
                is_primary=True
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
        self.product_model.objects.select_for_update().get(pk=product.pk)
        relations = list(
            self._relations(product).select_for_update(of=("self",)).order_by(
                "position", "id"
            )
        )
        existing_ids = {relation.id for relation in relations}
        if len(relation_ids) != len(set(relation_ids)) or set(relation_ids) != existing_ids:
            raise self.ValidationError(
                {"files": "Provide every product file exactly once."}
            )
        by_id = {relation.id: relation for relation in relations}
        updated_at = timezone.now()
        for position, relation_id in enumerate(relation_ids):
            relation = by_id[relation_id]
            relation.position = position
            relation.updated_at = updated_at
        self.relation_model.objects.bulk_update(relations, ["position", "updated_at"])
        return self.list_for_product(product)


class VendorProductFileService(ProductFileService):
    """The same media rules, pointed at a vendor submission."""

    product_model = VendorProduct
    relation_model = VendorProductFile
    product_field = "vendor_product"
