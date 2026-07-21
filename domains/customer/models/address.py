from django.db import models


class CustomerAddress(models.Model):
    class Meta:
        db_table = "customer_address"
        verbose_name_plural = "customer addresses"

    customer = models.ForeignKey(
        "Customer",
        on_delete=models.CASCADE,
        related_name="addresses",
    )
    title = models.CharField(max_length=100)
    country = models.ForeignKey(
        "location.Country",
        on_delete=models.PROTECT,
        related_name="customer_addresses",
    )
    state = models.ForeignKey(
        "location.State",
        on_delete=models.PROTECT,
        related_name="customer_addresses",
    )
    city = models.ForeignKey(
        "location.City",
        on_delete=models.PROTECT,
        related_name="customer_addresses",
    )
    postal_code = models.CharField(max_length=20)
    address_line1 = models.CharField(max_length=255)
    address_line2 = models.CharField(max_length=255, null=True, blank=True)
    house_number = models.CharField(max_length=20, null=True, blank=True)
    latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if self.is_default:
            CustomerAddress.objects.filter(customer=self.customer, is_default=True).exclude(
                id=self.id
            ).update(is_default=False)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.title}: {self.address_line1}, {self.city.name}"
