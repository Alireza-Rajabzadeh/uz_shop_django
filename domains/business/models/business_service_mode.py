from django.core.exceptions import ValidationError
from django.db import models

from .base import TimestampedModel


class BusinessServiceMode(TimestampedModel):
    """A way a business serves its customers.

    Shared reference vocabulary rather than per-business data: business
    profiles select from these rows through ``BusinessProfileServiceMode``.
    ``code`` is the stable contract other code keys off, so it is written once
    and never edited; ``name``, ``description``, and ``is_active`` stay
    editable. A mode is retired by clearing ``is_active``, never by deleting
    it, because profiles point at it. Service modes describe fulfilment style
    only — payment methods such as cash, card, or BNPL are a different
    vocabulary.
    """

    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    description = models.TextField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "business_service_mode"
        ordering = ["id"]

    def save(self, *args, **kwargs):
        if self.pk:
            stored = (
                type(self)
                .objects.filter(pk=self.pk)
                .values_list("code", flat=True)
                .first()
            )
            if stored is not None and stored != self.code:
                raise ValidationError(
                    {"code": "Code cannot be changed after creation."}
                )
        super().save(*args, **kwargs)

    def __str__(self):
        return self.code
