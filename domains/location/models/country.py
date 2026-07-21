from django.db import models


class Country(models.Model):
    class Meta:
        db_table = "location_country"
        verbose_name_plural = "countries"

    name = models.CharField(max_length=100)
    code = models.CharField(max_length=2, unique=True)
    phone_code = models.CharField(max_length=10)

    def __str__(self):
        return self.name
