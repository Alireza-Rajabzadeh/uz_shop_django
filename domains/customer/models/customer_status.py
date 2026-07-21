from django.db import models


class CustomerStatus(models.Model):
    class Meta:
        db_table = "customer_status"
        verbose_name_plural = "customer statuses"

    name = models.CharField(max_length=50, unique=True)
    title = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title
