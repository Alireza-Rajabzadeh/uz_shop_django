from django.db import models


class CustomerPreference(models.Model):
    class Meta:
        db_table = "customer_preference"

    customer = models.OneToOneField(
        "Customer",
        on_delete=models.CASCADE,
        related_name="preferences",
    )
    receive_order_emails = models.BooleanField(default=True)
    receive_sms_notifications = models.BooleanField(default=True)
    receive_push_notifications = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Preferences for {self.customer.customer_code}"
