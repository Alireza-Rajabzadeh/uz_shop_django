from django.db import models


class ProviderStatus(models.Model):
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=50, unique=True)

    class Meta:
        db_table = "notifications_provider_status"
        ordering = ["name"]

    def __str__(self):
        return self.name
