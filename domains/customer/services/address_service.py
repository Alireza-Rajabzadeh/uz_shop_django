from core.services.base import BaseService
from domains.customer.models import CustomerAddress


class CustomerAddressService(BaseService):
    model = CustomerAddress

    def list_for_customer(self, customer):
        return self.model.objects.filter(customer=customer).order_by("-is_default", "-created_at")
