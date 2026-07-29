from django.db import models
from django.db.models.functions import Lower, Trim


class Country(models.Model):
    class Meta:
        db_table = "location_country"
        verbose_name_plural = "countries"
        constraints = [
            models.UniqueConstraint(
                Lower(Trim("name")), name="location_country_normalized_name_unique"
            ),
            models.CheckConstraint(
                condition=models.Q(code__regex=r"^[A-Z]{2}$"),
                name="location_country_code_format",
            ),
        ]

    name = models.CharField(max_length=100)
    code = models.CharField(max_length=2, unique=True)
    phone_code = models.CharField(max_length=10)
    fa_title = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return self.name
