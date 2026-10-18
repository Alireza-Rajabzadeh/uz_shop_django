from rest_framework import serializers

from domains.catalog.api.serializers import (
    ProductDetailsSerializer,
    ProductFileReadSerializer,
    primary_category,
)
from domains.catalog.models import (
    VendorProduct,
    VendorProductDetails,
    VendorProductFile,
    VendorProductStatus,
)
from domains.catalog.services.vendor_product_submission_service import (
    vendor_product_submission_service,
)


class ReviewSubmissionFileSerializer(ProductFileReadSerializer):
    class Meta(ProductFileReadSerializer.Meta):
        model = VendorProductFile


class ReviewSubmissionDetailsSerializer(ProductDetailsSerializer):
    class Meta(ProductDetailsSerializer.Meta):
        model = VendorProductDetails


class VendorProductReviewListSerializer(serializers.ModelSerializer):
    """One row of the admin confirmation queue."""

    status_name = serializers.CharField(source="status.name", read_only=True)
    brand_name = serializers.CharField(
        source="brand.name", read_only=True, allow_null=True
    )
    brand_fa_name = serializers.CharField(
        source="brand.fa_name", read_only=True, allow_null=True
    )
    category_name = serializers.SerializerMethodField()
    category_fa_name = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()
    vendor_name = serializers.SerializerMethodField()
    vendor_code = serializers.CharField(
        source="vendor.vendor_code", read_only=True, allow_null=True
    )
    business_name = serializers.SerializerMethodField()
    changed_fields = serializers.SerializerMethodField()

    class Meta:
        model = VendorProduct
        fields = [
            "id", "name", "status", "status_name", "product",
            "categories", "category_name", "category_fa_name",
            "brand", "brand_name", "brand_fa_name",
            "description", "admin_response",
            "confirmed_at", "created_at", "updated_at",
            "vendor", "vendor_name", "vendor_code", "business_name",
            "thumbnail_url", "changed_fields",
        ]

    def get_category_name(self, obj):
        category = primary_category(obj)
        return category.name if category else None

    def get_category_fa_name(self, obj):
        category = primary_category(obj)
        return category.fa_name if category else None

    def get_thumbnail_url(self, obj):
        media = obj.product_files.select_related(
            "file", "file__status"
        ).order_by("position", "id").first()
        if media is None:
            return None
        from domains.files.services import FileService
        try:
            return FileService().url(media.file)
        except FileService.Error:
            return None

    def get_vendor_name(self, obj):
        if obj.vendor_id is None:
            return None
        return f"{obj.vendor.first_name} {obj.vendor.last_name}".strip() or None

    def get_business_name(self, obj):
        profiles = getattr(obj.vendor, "business_profiles", None)
        if profiles is None:
            return None
        profile = profiles.first()
        return profile.business_name if profile else None

    def get_changed_fields(self, obj):
        if not obj.product_id:
            return sorted(vendor_product_submission_service.APPLYABLE_FIELDS)
        return sorted(vendor_product_submission_service.changed_fields(obj))


class VendorProductReviewDetailSerializer(VendorProductReviewListSerializer):
    """The queue row plus everything needed to decide field by field."""

    details = serializers.SerializerMethodField()
    pictures = serializers.SerializerMethodField()
    live = serializers.SerializerMethodField()

    class Meta(VendorProductReviewListSerializer.Meta):
        fields = VendorProductReviewListSerializer.Meta.fields + [
            "json_description", "details", "pictures", "live", "confirmed_by",
        ]

    def get_details(self, obj):
        rows = obj.details.select_related("detail").order_by("detail_id")
        return ReviewSubmissionDetailsSerializer(rows, many=True).data

    def get_pictures(self, obj):
        rows = obj.product_files.select_related(
            "file", "file__status"
        ).order_by("position", "id")
        return ReviewSubmissionFileSerializer(rows, many=True).data

    def get_live(self, obj):
        """What the catalog currently serves, for the fields on offer.

        Null for a first-time draft: there is nothing live to compare to, so
        every field is new rather than changed.
        """
        product = obj.product
        if product is None:
            return None
        brand = product.brand
        return {
            "id": product.id,
            "name": product.name,
            "brand": (
                {"id": brand.id, "name": brand.name, "fa_name": brand.fa_name}
                if brand else None
            ),
            "description": product.description,
            "json_description": product.json_description,
            "categories": [
                {"id": category.id, "name": category.name, "fa_name": category.fa_name}
                for category in product.categories.order_by("id")
            ],
            "details": ProductDetailsSerializer(
                product.details.select_related("detail").order_by("detail_id"),
                many=True,
            ).data,
            "pictures": ProductFileReadSerializer(
                product.product_files.select_related(
                    "file", "file__status"
                ).order_by("position", "id"),
                many=True,
            ).data,
        }


class VendorProductNoteSerializer(serializers.Serializer):
    """Free-text note handed back to the vendor with the decision."""

    response = serializers.CharField(required=False, allow_blank=True, default="")


class VendorProductApplySerializer(VendorProductNoteSerializer):
    fields = serializers.ListField(
        child=serializers.ChoiceField(
            choices=sorted(vendor_product_submission_service.APPLYABLE_FIELDS)
        ),
        allow_empty=False,
    )


class VendorProductDecideSerializer(VendorProductNoteSerializer):
    status = serializers.ChoiceField(
        choices=[
            (VendorProductStatus.Code.NEED_RECHECK, "Need recheck"),
            (VendorProductStatus.Code.REJECT, "Reject"),
        ]
    )

