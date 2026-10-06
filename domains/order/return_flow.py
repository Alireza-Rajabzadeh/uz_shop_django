"""Asking for a returned item, and deciding whether one may be asked for.

The rules — the three-day window from delivery, one open request per order,
no more returned than was sold, cost layers going back exactly as they came
out — do not depend on which order table the request points at. A flow
supplies its order, line, request, item, evidence and history tables and
gets the whole flow; nothing restates a transition.
"""

from datetime import timedelta

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from django.utils.translation import gettext as _

from .flow import file_url
from .models import (
    Order,
    OrderHistory,
    OrderItem,
    ReturnRequest,
    ReturnRequestEvidence,
    ReturnRequestItem,
)


class BaseReturnRequestService:
    class ValidationError(Exception):
        def __init__(self, errors):
            self.errors = errors
            super().__init__(str(errors))

    class NotFoundError(Exception):
        pass

    # Both flows' return models spell the same six statuses with the same
    # values, so the rules below are written once against the literals rather
    # than against either model's TextChoices.
    COUNTED_STATUSES = ("requested", "approved", "received", "completed")
    ACTIVE_STATUSES = ("requested", "approved", "received")
    RETURN_WINDOW = timedelta(days=3)
    ACTION_TRANSITIONS = {
        "approve": ("requested", "approved"),
        "reject": ("requested", "rejected"),
        "received": ("approved", "received"),
        "complete": ("received", "completed"),
    }

    # Required on a subclass: which order, which line, and which of the three
    # return tables plus the history table that dates the delivery.
    order_model = None
    order_item_model = None
    request_model = None
    item_model = None
    evidence_model = None
    history_model = None

    def _scoped_requests(self):
        """The return rows this instance may read or decide on.

        Each call site narrows further by order or by customer. The hook
        exists so a flow acting for a slice of the order table — a seller for
        their own business — can scope the request rows in the query rather
        than having the caller prove the order was theirs first.
        """
        return self.request_model.objects.all()

    @classmethod
    def available_admin_actions(cls, status):
        return [
            action
            for action, (source, _target) in cls.ACTION_TRANSITIONS.items()
            if source == status
        ]

    # ───────────────────────── reading ─────────────────────────

    def admin_payloads(self, order):
        requests = (
            self._scoped_requests().filter(order=order)
            .select_related("customer")
            .prefetch_related("items", "evidence__file__status")
            .order_by("-requested_at", "-id")
        )
        return [self.admin_payload(request) for request in requests]

    def admin_payload(self, request):
        customer = request.customer
        return {
            "id": request.id,
            "status": request.status,
            "customer": {
                "id": customer.id,
                "name": f"{customer.first_name} {customer.last_name}".strip(),
                "phone": customer.phone,
                "customer_code": customer.customer_code,
            },
            "reason": request.reason,
            "customer_note": request.customer_note,
            "admin_note": request.admin_note,
            "customer_response": request.customer_response,
            "refund_destination_type": request.refund_destination_type,
            "refund_destination_masked": f"****{request.refund_destination_value[-4:]}",
            "items": [
                {
                    "id": item.id,
                    "order_item_id": item.order_item_id,
                    "quantity": item.quantity,
                    "reason": item.reason,
                }
                for item in request.items.all()
            ],
            "evidence": [
                {
                    "id": evidence.id,
                    "file_id": str(evidence.file_id),
                    "position": evidence.position,
                    "original_name": evidence.file.original_name,
                    "content_type": evidence.file.content_type,
                    "size": evidence.file.size,
                    "url": file_url(evidence.file),
                }
                for evidence in request.evidence.all()
            ],
            "available_actions": self.available_admin_actions(request.status),
            "requested_at": request.requested_at.isoformat(),
            "approved_at": request.approved_at.isoformat() if request.approved_at else None,
            "received_at": request.received_at.isoformat() if request.received_at else None,
            "completed_at": request.completed_at.isoformat() if request.completed_at else None,
            "created_at": request.created_at.isoformat(),
            "updated_at": request.updated_at.isoformat(),
        }

    def list(self, customer):
        return (
            self._scoped_requests().filter(customer=customer)
            .select_related("order")
            .prefetch_related("items", "evidence__file__status")
            .order_by("-requested_at", "-id")
        )

    def get(self, customer, return_request_id):
        try:
            return (
                self._scoped_requests().filter(customer=customer)
                .select_related("order")
                .prefetch_related("items", "evidence__file__status")
                .get(id=return_request_id)
            )
        except self.request_model.DoesNotExist as exc:
            raise self.NotFoundError("Return request not found.") from exc

    # ───────────────────────── admin decisions ─────────────────────────

    @transaction.atomic
    def execute_admin_action(
        self, order_id, return_request_id, action_code, *, admin_note=..., customer_response=...
    ):
        transition = self.ACTION_TRANSITIONS.get(action_code)
        if transition is None:
            raise self.ValidationError({"action": [_('Unknown return action.')]})
        request = (
            self._scoped_requests().select_for_update()
            .filter(id=return_request_id, order_id=order_id)
            .first()
        )
        if request is None:
            raise self.NotFoundError("Return request not found.")
        source, target = transition
        if request.status != source:
            raise self.ValidationError({
                "action": [_('This action is not available for the current return status.')]
            })
        request.status = target
        update_fields = ["status", "updated_at"]
        timestamp_field = {
            "approved": "approved_at",
            "received": "received_at",
            "completed": "completed_at",
        }.get(target)
        if timestamp_field:
            setattr(request, timestamp_field, timezone.now())
            update_fields.append(timestamp_field)
        if admin_note is not ...:
            request.admin_note = admin_note
            update_fields.append("admin_note")
        if customer_response is not ...:
            request.customer_response = customer_response
            update_fields.append("customer_response")
        request.save(update_fields=update_fields)
        if target == "completed":
            # Returned goods are accepted: restore the consumed supply cost
            # layers for exactly the returned quantities. Runs inside this
            # method's transaction; completion happens once per request.
            # Items sold before supply tracking existed reverse nothing.
            from domains.inventory.services import InventorySupplyService

            supply_service = InventorySupplyService()
            for item in request.items.select_related("order_item"):
                if not item.order_item.supply_consumptions.exists():
                    continue
                supply_service.reverse_order_item_consumption(
                    item.order_item, quantity=item.quantity
                )
        return request

    # ───────────────────────── eligibility ─────────────────────────

    @classmethod
    def delivery_time(cls, order):
        return (
            cls.history_model.objects.filter(order=order, action__code="deliver")
            .order_by("-created_at", "-id")
            .values_list("created_at", flat=True)
            .first()
        )

    @classmethod
    def is_eligible(cls, order, *, now=None):
        if order.status.name != "delivered":
            return False
        if cls.request_model.objects.filter(
            order=order,
            status__in=cls.ACTIVE_STATUSES,
        ).exists():
            return False
        delivered_at = cls.delivery_time(order)
        return bool(
            delivered_at
            and (now or timezone.now()) < delivered_at + cls.RETURN_WINDOW
        )

    # ───────────────────────── requesting ─────────────────────────

    @transaction.atomic
    def create(
        self, customer, *, order_id, reason, refund_destination_type,
        refund_destination_value, customer_note=None, items, images=None,
    ):
        try:
            order = (
                self.order_model.objects.select_for_update()
                .select_related("status")
                .get(id=order_id, customer=customer)
            )
        except self.order_model.DoesNotExist as exc:
            raise self.NotFoundError("Order not found.") from exc

        if not self.is_eligible(order):
            raise self.ValidationError({
                "order_id": [_('This order is not currently eligible for return.')]
            })

        requested_by_id = {item["order_item_id"]: item for item in items}
        order_items = list(
            self.order_item_model.objects.select_for_update()
            .filter(id__in=requested_by_id, order=order)
            .order_by("id")
        )
        if len(order_items) != len(requested_by_id):
            raise self.ValidationError({
                "items": [_('Every order item must belong to the selected order.')]
            })

        already_returned = {
            row["order_item_id"]: row["total"]
            for row in self.item_model.objects.filter(
                order_item_id__in=requested_by_id,
                return_request__status__in=self.COUNTED_STATUSES,
            )
            .values("order_item_id")
            .annotate(total=Sum("quantity"))
        }
        quantity_errors = []
        for order_item in order_items:
            requested_quantity = requested_by_id[order_item.id]["quantity"]
            available = order_item.quantity - already_returned.get(order_item.id, 0)
            if requested_quantity > available:
                quantity_errors.append(
                    _(
                        "Order item %(item_id)s has only %(available)s available "
                        "to return."
                    )
                    % {"item_id": order_item.id, "available": max(available, 0)}
                )
        if quantity_errors:
            raise self.ValidationError({"items": quantity_errors})

        return_request = self._scoped_requests().create(
            order=order,
            customer=customer,
            reason=reason,
            customer_note=customer_note,
            refund_destination_type=refund_destination_type,
            refund_destination_value=refund_destination_value,
        )
        self.item_model.objects.bulk_create([
            self.item_model(
                return_request=return_request,
                order_item=order_item,
                quantity=requested_by_id[order_item.id]["quantity"],
                reason=requested_by_id[order_item.id].get("reason"),
            )
            for order_item in order_items
        ])
        from domains.files.services import FileService

        for position, image in enumerate(images or []):
            try:
                file = FileService().upload(
                    image,
                    object_prefix=f"orders/{order.id}/returns/{return_request.id}",
                )
            except FileService.Error as exc:
                raise self.ValidationError({"images": [str(exc)]}) from exc
            self.evidence_model.objects.create(
                return_request=return_request,
                file=file,
                position=position,
            )
        return self.get(customer, return_request.id)


class ReturnRequestService(BaseReturnRequestService):
    """Returns for shop orders."""

    order_model = Order
    order_item_model = OrderItem
    request_model = ReturnRequest
    item_model = ReturnRequestItem
    evidence_model = ReturnRequestEvidence
    history_model = OrderHistory
