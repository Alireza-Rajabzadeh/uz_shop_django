from django.db import models

from .base import ImmutableCodeModel


class Feature(ImmutableCodeModel):
    """A capability a package can grant, e.g. ``shop.products``.

    Codes are the contract for future backend authorization checks and for
    the panels' feature-availability logic. Names and descriptions are
    editable display text only.
    """

    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, default="")

    class Meta:
        db_table = "packages_feature"
        ordering = ["id"]

    def __str__(self):
        return self.code
