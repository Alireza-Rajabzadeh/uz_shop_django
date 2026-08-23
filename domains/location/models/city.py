from django.db import models
from django.db.models import F
from django.db.models.functions import Lower, Trim


class City(models.Model):
    class Meta:
        db_table = "location_city"
        verbose_name_plural = "cities"
        constraints = [
            models.UniqueConstraint(
                F("state"), Lower(Trim("name")),
                name="location_city_state_normalized_name_unique",
            ),
        ]

    state = models.ForeignKey(
        "State",
        on_delete=models.CASCADE,
        related_name="cities",
    )
    name = models.CharField(max_length=100)
    fa_title = models.CharField(max_length=100, blank=True)
    latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)

    def __str__(self):
        return f"{self.name}, {self.state.name}"
