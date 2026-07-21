from django.db import models


class State(models.Model):
    class Meta:
        db_table = "location_state"

    country = models.ForeignKey(
        "Country",
        on_delete=models.CASCADE,
        related_name="states",
    )
    name = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.name}, {self.country.name}"
