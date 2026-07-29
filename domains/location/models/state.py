from django.db import models
from django.db.models import F
from django.db.models.functions import Lower, Trim


class State(models.Model):
    class Meta:
        db_table = "location_state"
        constraints = [
            models.UniqueConstraint(
                F("country"), Lower(Trim("name")),
                name="location_state_country_normalized_name_unique",
            ),
        ]

    country = models.ForeignKey(
        "Country",
        on_delete=models.CASCADE,
        related_name="states",
    )
    name = models.CharField(max_length=100)
    fa_title = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return f"{self.name}, {self.country.name}"
