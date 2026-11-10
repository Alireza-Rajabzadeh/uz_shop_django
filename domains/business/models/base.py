from django.core.exceptions import ValidationError
from django.db import models


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class ImmutableKeyModel(TimestampedModel):
    key = models.SlugField(max_length=80)

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if self.pk:
            original = type(self).objects.filter(pk=self.pk).values_list("key", flat=True).first()
            if original is not None and original != self.key:
                raise ValidationError({"key": "Key cannot be changed after creation."})
        return super().save(*args, **kwargs)
