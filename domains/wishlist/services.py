from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils.translation import gettext as _

from domains.catalog.models import Product

from .models import Wishlist


class WishlistService:
    class ValidationError(Exception):
        def __init__(self, errors):
            self.errors = errors
            super().__init__(str(errors))

    def list_admin(self, **filters):
        queryset = (
            Wishlist.objects.select_related("product", "product__status", "product__brand", "customer")
            .prefetch_related("product__categories")
        )
        search = (filters.get("search") or "").strip()
        if search:
            queryset = queryset.filter(
                Q(product__name__icontains=search)
                | Q(customer__phone__icontains=search)
                | Q(customer__first_name__icontains=search)
                | Q(customer__last_name__icontains=search)
            )
        product_id = filters.get("product_id")
        if product_id:
            queryset = queryset.filter(product_id=product_id)
        created_from = filters.get("created_from")
        if created_from:
            queryset = queryset.filter(created_at__date__gte=created_from)
        created_to = filters.get("created_to")
        if created_to:
            queryset = queryset.filter(created_at__date__lte=created_to)
        ordering = (filters.get("ordering") or "").strip()
        if ordering in {"id", "-id", "created_at", "-created_at"}:
            queryset = queryset.order_by(ordering)
        else:
            queryset = queryset.order_by("-created_at", "id")
        return queryset

    def list_for_customer(self, customer):
        return (
            Wishlist.objects.filter(customer=customer)
            .select_related("product", "product__status", "product__brand")
            .prefetch_related("product__categories")
        )

    @staticmethod
    def get_product(product_id):
        try:
            return Product.objects.select_related("status").get(id=product_id)
        except Product.DoesNotExist as exc:
            raise WishlistService.ValidationError(
                {"product_id": [_("Product not found.")]}
            ) from exc

    @transaction.atomic
    def add(self, customer, product_id):
        product = self.get_product(product_id)
        try:
            return Wishlist.objects.create(customer=customer, product=product)
        except IntegrityError as exc:
            raise self.ValidationError({
                "product_id": [_("This product is already in your wishlist.")]
            }) from exc

    def remove(self, customer, product_id):
        deleted, _lookup = Wishlist.objects.filter(
            customer=customer, product_id=product_id
        ).delete()
        if deleted == 0:
            raise self.ValidationError({
                "product_id": [_("Wishlist item not found.")]
            })

    def exists(self, customer, product_id):
        return Wishlist.objects.filter(
            customer=customer, product_id=product_id
        ).exists()