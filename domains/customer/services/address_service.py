from django.db import transaction

from core.services.base import BaseService
from domains.customer.models import Customer, CustomerAddress


class CustomerAddressService(BaseService):
    model = CustomerAddress

    def list_for_customer(self, customer):
        return self.model.objects.filter(customer=customer).select_related(
            "country", "state", "city"
        ).order_by("-is_default", "-created_at")

    def get_for_customer(self, customer, address_id):
        return self.model.objects.filter(
            customer=customer, id=address_id
        ).select_related("country", "state", "city").first()

    @transaction.atomic
    def create(self, customer, **data):
        Customer.objects.select_for_update().get(pk=customer.pk)
        if data.get("is_default"):
            self.model.objects.filter(customer=customer, is_default=True).update(is_default=False)
        return self.model.objects.create(customer=customer, **data)

    @transaction.atomic
    def update(self, instance, **data):
        Customer.objects.select_for_update().get(pk=instance.customer_id)
        if data.get("is_default"):
            self.model.objects.filter(
                customer_id=instance.customer_id, is_default=True
            ).exclude(pk=instance.pk).update(is_default=False)
        return self._update(instance, **data)

    def delete(self, instance):
        self._delete(instance)
