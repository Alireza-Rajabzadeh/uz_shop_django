from django.db import models


class CategoryDetail(models.Model):

    TYPE_TEXT = "text"
    TYPE_NUMBER = "number"
    TYPE_SELECT = "select"

    TYPE_CHOICES = (
        (TYPE_TEXT, "Text"),
        (TYPE_NUMBER, "Number"),
        (TYPE_SELECT, "Select"),
    )

    name = models.CharField(max_length=100, unique=True)

    type = models.CharField(max_length=20, choices=TYPE_CHOICES)

    required = models.BooleanField(default=False)

    modelable_filter = models.ForeignKey(
        "FilterSource",
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    is_filterable = models.BooleanField(default=True)

    def __str__(self):
        return self.name