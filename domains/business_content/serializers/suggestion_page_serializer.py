from rest_framework import serializers

from ..models import SuggestionPage


class SuggestionPageSerializer(serializers.ModelSerializer):
    """Read-only projection of the pages the panel offers to create.

    ``activate`` is a management flag the view filters on server-side, so it
    is not sent to the panels. ``context`` is: the editor filters the component
    palette by it, matching the ``allowedContexts`` each contract declares.
    """

    class Meta:
        model = SuggestionPage
        fields = ["id", "title", "descriptions", "required", "slug", "context"]
        read_only_fields = fields
