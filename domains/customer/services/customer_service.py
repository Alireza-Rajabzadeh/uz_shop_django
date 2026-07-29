from django.db.models import Q

from core.services.base import BaseService
from domains.customer.models import Customer


class CustomerService(BaseService):
    model = Customer

    def search(self, ordering=None, search=None, **filters):
        ordering_fields = {
            "id": "id",
            "customer_code": "customer_code",
            "first_name": "first_name",
            "last_name": "last_name",
            "email": "email",
            "phone": "phone",
            "status_name": "status__name",
            "gender": "gender",
            "date_of_birth": "date_of_birth",
            "email_verified_at": "email_verified_at",
            "phone_verified_at": "phone_verified_at",
            "last_login": "last_login",
            "created_at": "created_at",
            "updated_at": "updated_at",
        }
        orm_filters = {}
        for field in ("id", "status_id", "gender"):
            if field in filters:
                orm_filters[field] = filters[field]
        for field in ("customer_code", "first_name", "last_name", "email", "phone"):
            if filters.get(field):
                orm_filters[f"{field}__icontains"] = filters[field]
        for field in ("email_verified", "phone_verified"):
            if field in filters:
                orm_filters[f"{field}_at__isnull"] = not filters[field]
        if "has_logged_in" in filters:
            orm_filters["last_login__isnull"] = not filters["has_logged_in"]
        for prefix in ("date_of_birth", "last_login", "created_at", "updated_at"):
            model_prefix = prefix if prefix == "date_of_birth" else f"{prefix}__date"
            if f"{prefix}_from" in filters:
                orm_filters[f"{model_prefix}__gte"] = filters[f"{prefix}_from"]
            if f"{prefix}_to" in filters:
                orm_filters[f"{model_prefix}__lte"] = filters[f"{prefix}_to"]

        queryset = self.model.objects.filter(**orm_filters).select_related("status")
        if search:
            queryset = queryset.filter(
                Q(customer_code__icontains=search)
                | Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
                | Q(email__icontains=search)
                | Q(phone__icontains=search)
            )
        descending = ordering and ordering.startswith("-")
        requested = ordering.lstrip("-") if ordering else "id"
        field = ordering_fields.get(requested, "id")
        return queryset.order_by(f"-{field}" if descending else field)

    def get_customer(self, customer_id):
        return self.model.objects.select_related("status").filter(pk=customer_id).first()

    def update_customer(self, customer, **data):
        return self._update(customer, **data)
