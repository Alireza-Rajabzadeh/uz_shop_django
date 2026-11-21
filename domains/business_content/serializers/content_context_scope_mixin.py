from ..contracts import enforce_draft_context
from ..models import SuggestionPage


class ContentContextScopeMixin:
    """Restrict ``draft_content`` to the components allowed for this row's context.

    A page's context is whatever the `SuggestionPage` holding its canonical
    slug declares, so the panel's suggestion list and the API agree on what a
    page is without a foreign key — changing a suggestion's context applies
    immediately to every page carrying that slug. A slug outside the standard
    set falls back to the default context, which every component currently
    allows, so an arbitrary page is never locked out of its own vocabulary.

    The slug is read from the payload on create and from the stored row on
    update, so a PATCH that omits ``slug`` still resolves against the saved one.
    """

    def validate_draft_content(self, value):
        slug = getattr(self, "initial_data", {}).get("slug")
        if not isinstance(slug, str) or not slug.strip():
            slug = getattr(self.instance, "slug", "")
        # `iexact` because the panels normalize the slug they match on (trim +
        # lowercase) before resolving a context, and the two must agree.
        context = (
            SuggestionPage.objects.filter(slug__iexact=str(slug).strip())
            .values_list("context", flat=True)
            .first()
            or SuggestionPage.Context.PAGE.value
        )
        return enforce_draft_context(value, context)
