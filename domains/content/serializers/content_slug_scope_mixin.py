from django.utils.translation import gettext as _
from rest_framework import serializers


class ContentSlugScopeMixin:
    """Slugs are globally unique across platform content.

    The serializer keeps a duplicate a 400 instead of an IntegrityError. The
    serializers declare ``slug`` and ``Meta.validators = []`` explicitly so DRF
    does not build its own uniqueness validators from the model constraint —
    keeping one source of truth for the rule.
    """

    def validate_slug(self, slug):
        matches = self.Meta.model.objects.filter(slug=slug)
        if self.instance is not None:
            matches = matches.exclude(pk=self.instance.pk)
        if matches.exists():
            raise serializers.ValidationError(
                _("A content item with this slug already exists.")
            )
        return slug
