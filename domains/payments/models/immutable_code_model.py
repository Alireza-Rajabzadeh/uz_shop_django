from django.db import models


class ImmutableCodeModel(models.Model):
    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if self.pk:
            old_code = type(self).objects.filter(pk=self.pk).values_list("code", flat=True).first()
            if old_code is not None and old_code != self.code:
                raise ValueError("Code is immutable.")
        super().save(*args, **kwargs)
