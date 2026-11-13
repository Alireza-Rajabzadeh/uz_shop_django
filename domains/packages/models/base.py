from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext as _


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class ImmutableCodeModel(TimestampedModel):
    """A record identified by a stable ``code``.

    Application logic keys off ``code``, never off a display name or a
    database id: ids are not portable between environments and names are
    editable. Mirrors `domains.business_payments.ImmutableCodeModel`, kept
    local so this domain does not depend on another domain's models.
    """

    code = models.CharField(max_length=50, unique=True)

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if self.pk:
            stored = (
                type(self).objects.filter(pk=self.pk)
                .values_list("code", flat=True)
                .first()
            )
            if stored is not None and stored != self.code:
                raise ValidationError({"code": _("Code cannot be changed after creation.")})
        super().save(*args, **kwargs)
