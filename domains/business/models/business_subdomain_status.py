from django.db import models


class BusinessSubdomainStatus(models.Model):
    """Reference configuration rows for subdomain lifecycle status."""

    code = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=64)
    title = models.CharField(max_length=64)

    class Meta:
        db_table = "business_subdomain_status"
        verbose_name = "Business Subdomain Status"
        verbose_name_plural = "Business Subdomain Statuses"

    def __str__(self):
        return self.code
