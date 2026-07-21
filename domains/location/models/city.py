from django.db import models


class City(models.Model):
    class Meta:
        db_table = "location_city"
        verbose_name_plural = "cities"

    state = models.ForeignKey(
        "State",
        on_delete=models.CASCADE,
        related_name="cities",
    )
    name = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.name}, {self.state.name}"
