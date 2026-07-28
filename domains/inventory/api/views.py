from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import DjangoModelPermissions
from rest_framework.views import APIView

from core.responses import api_response
from domains.catalog.models import ProductVariants
from domains.inventory.services import InventoryService

from .serializers import VariantInventoryDetailSerializer


inventory_service = InventoryService()


class InventoryModelPermissions(DjangoModelPermissions):
    perms_map = {
        "GET": ["%(app_label)s.view_%(model_name)s"],
        "OPTIONS": [],
        "HEAD": [],
    }

    def _queryset(self, view):
        return view.model._default_manager.all()


class VariantInventoryDetail(APIView):
    model = ProductVariants
    permission_classes = [InventoryModelPermissions]

    def get(self, request, variant_id):
        try:
            variant = ProductVariants.objects.select_related("inventory_strategy").get(
                pk=variant_id
            )
        except ProductVariants.DoesNotExist as exc:
            raise NotFound("Variant not found.") from exc
        try:
            details = inventory_service.get_variant_details(variant)
        except InventoryService.ValidationError as exc:
            raise ValidationError(exc.errors) from exc
        return api_response(True, "", VariantInventoryDetailSerializer(details).data)
