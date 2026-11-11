from django.db import models


class BusinessPaymentStatus(models.Model):
    class Meta:
        db_table = "business_payment_status"
        verbose_name_plural = "business payment statuses"
        ordering = ["id"]

    name = models.CharField(max_length=50, unique=True)
    title = models.CharField(max_length=100)
    description = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title
