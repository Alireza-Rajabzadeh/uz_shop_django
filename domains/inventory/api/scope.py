"""Business scope resolution for the admin inventory API.

Inventory is a business-level feature: every ``Inventory``, ``Warehouse``,
``InventorySupply``, ``BusinessOffer`` and supply report row belongs to one
``BusinessProfile``. The admin API therefore names the business it operates on
through the ``business_id`` query parameter.

- A named business is a plain ``inventory.view_inventory`` scope.
- Omitting the parameter (or sending ``all``) asks for the cross-business
  aggregate, which additionally needs ``inventory.view_all_business`` and is
  read-only. There is no aggregate write path: a write always targets exactly
  one business.

The vendor API resolves its business from the authenticated vendor instead and
does not use this module. Pricing is deliberately single-business, so its views
always require a named business.
"""

from rest_framework.exceptions import NotFound, ValidationError

from domains.business.models import BusinessProfile


SCOPE_PARAM = "business_id"
AGGREGATE_VALUES = (None, "", "all")

VIEW_INVENTORY = "inventory.view_inventory"
ADJUST_STOCK = "inventory.adjust_stock"
VIEW_ALL_BUSINESS = "inventory.view_all_business"

READ_METHODS = ("GET", "HEAD", "OPTIONS")

#: The permission a scoped read adds when no business is named.
AGGREGATE_PERMISSION = VIEW_ALL_BUSINESS


def is_aggregate(request):
    """True when the request asks for every business (no ``business_id``)."""
    return request.query_params.get(SCOPE_PARAM) in AGGREGATE_VALUES


def resolve_business(request):
    """The business named by the request, or ``None`` for the aggregate scope.

    Raises ``ValidationError`` for a malformed id and ``NotFound`` for an
    unknown one, both surfaced as the standard error envelope.
    """
    raw = request.query_params.get(SCOPE_PARAM)
    if raw in AGGREGATE_VALUES:
        return None
    try:
        business_id = int(raw)
    except (TypeError, ValueError):
        raise ValidationError({SCOPE_PARAM: ["A valid business id is required."]})
    business = BusinessProfile.objects.filter(pk=business_id).first()
    if business is None:
        raise NotFound("Business not found.")
    return business


def require_business(request):
    """Resolve a mandatory business scope for a pricing request."""
    business = resolve_business(request)
    if business is None:
        raise ValidationError({SCOPE_PARAM: ["A business must be selected."]})
    return business


def scope_permits(request):
    """Whether the request's scope is allowed for its method.

    A named business needs no extra scope permission. An aggregate read needs
    ``inventory.view_all_business``; an aggregate write is never permitted.
    """
    if not is_aggregate(request):
        return True
    if request.method not in READ_METHODS:
        return False
    return bool(request.user and request.user.has_perm(VIEW_ALL_BUSINESS))
