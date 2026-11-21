from django.utils.translation import gettext as _
from rest_framework import serializers


class BusinessSlugScopeMixin:
    """Slug uniqueness is scoped to the owning business.

    The view always puts the caller's business in the serializer context, and
    ``business`` is never accepted from the payload — it is assigned on
    ``save()``. The DB constraint in the models backs this up, but a serializer
    check keeps duplicates a 400 instead of an IntegrityError.

    The serializers declare ``slug`` and ``Meta.validators = []`` explicitly so
    DRF does not build its own uniqueness validators from that constraint:
    they would validate across every business, because the authoring business
    lives in the view, not in the payload.
    """

    def validate_slug(self, slug):
        business = self.context.get("business")
        if business is None:
            return slug
        matches = self.Meta.model.objects.filter(slug=slug, business=business)
        if self.instance is not None:
            matches = matches.exclude(pk=self.instance.pk)
        if matches.exists():
            raise serializers.ValidationError(
                _("A content item with this slug already exists in this scope.")
            )
        return slug
