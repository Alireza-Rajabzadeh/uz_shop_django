"""The part of an order that is the same on either flow.

Expiring a reservation, moving an order to its next status and writing down
why are described once here. A marketplace order is not a shop order, but
"release the stock, set payment_expired, record that it timed out" is the
same sentence for both, so a flow supplies its tables and never restates a
transition.
"""

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from domains.cart.checkout import BaseCheckoutService


class BaseOrderService(BaseCheckoutService):
    """Reservation lifecycle, status actions and audit history.

    Required on a subclass beyond what ``BaseCheckoutService`` already asks
    for:

    ``status_action_model``
        Which rows say which action is available from which status.
    ``history_model``
        Which rows record that an action happened.
    """

    class NotFoundError(Exception):
        pass

    STATUS_PAID = "paid"
    STATUS_PAYMENT_FAILED = "payment_failed"
    STATUS_CANCELLED = "cancelled"
    STATUS_PAYMENT_EXPIRED = "payment_expired"
    # Deliberately spelled out: a class body does not see its bases' names,
    # and the same literals are what the seeders write.
    IN_PROGRESS_STATUSES = (
        "payment_pending",
        "payment_processing",
        STATUS_PAID,
        "confirmed",
        "preparing",
        "packed",
        "ready_for_shipment",
        "shipped",
        "in_transit",
        "out_for_delivery",
        "delivery_delayed",
    )

    status_action_model = None
    history_model = None

    # ───────────────────────── returns ─────────────────────────

    def return_service(self):
        """The returns service guarding the ``request_return`` action.

        ``None`` means this flow has no returns yet; the action is then never
        offered to anybody instead of being offered and refused.
        """
        return None

    def _return_eligible(self, order):
        service = self.return_service()
        return service is not None and service.is_eligible(order)

    # ───────────────────────── reservation lifecycle ─────────────────────────

    def expire_lazy(self, orders):
        now = timezone.now()
        stale = [
            order
            for order in orders
            if order.status.name == self.STATUS_PAYMENT_PENDING
            and order.reservation_expires_at is not None
            and order.reservation_expires_at <= now
        ]
        if stale:
            self.expire_orders(stale)

    def expire_orders(self, orders=None):
        if orders is None:
            with transaction.atomic():
                orders = list(
                    self.order_model.objects.select_for_update()
                    .select_related("status")
                    .filter(
                        status__name=self.STATUS_PAYMENT_PENDING,
                        reservation_expires_at__lte=timezone.now(),
                    )
                )
        if not orders:
            return []
        with transaction.atomic():
            expired = self._status(self.STATUS_PAYMENT_EXPIRED)
            for order in orders:
                self.release_reservations(order)
                order.status = expired
                order.reservation_expires_at = None
                order.save(update_fields=["status", "reservation_expires_at"])
        return orders

    def release_reservations(self, order):
        """Return an order's reserved stock back to the sellable pool."""
        self.inventory_service.release_reserved_stock(
            self._reservation_rows(order)
        )

    def consume_reservations(self, order):
        """Convert an order's reserved stock into a sale."""
        from domains.inventory.services import InventorySupplyService

        supply_service = InventorySupplyService()
        for order_item in order.items.prefetch_related("reservations"):
            reservations = list(order_item.reservations.all())
            self.inventory_service.consume_reserved_stock(reservations)
            # Finalized sale: consume FIFO cost layers for COGS tracking.
            supply_service.consume_order_item(order_item)

    @staticmethod
    def _reservation_rows(order):
        rows = []
        for order_item in order.items.prefetch_related("reservations"):
            rows.extend(order_item.reservations.all())
        return rows

    @staticmethod
    def reverse_order_supply_consumption(order):
        """Restore consumed cost layers for every item of a cancelled order."""
        from domains.inventory.services import InventorySupplyService

        supply_service = InventorySupplyService()
        for order_item in order.items.all():
            # Full reversal; items without consumption records are no-ops.
            supply_service.reverse_order_item_consumption(order_item)

    # ───────────────────────── status actions ─────────────────────────

    @staticmethod
    def _action_payload(assignment):
        action = assignment.order_action
        target = action.set_status
        return {
            "id": action.id,
            "code": action.code,
            "name": action.name,
            "fa_name": action.fa_name,
            "admin": action.admin,
            "customer": action.customer,
            "set_status": (
                {"id": target.id, "name": target.name, "fa_name": target.fa_name}
                if target is not None
                else None
            ),
        }

    def available_actions(self, order_id, *, actor, customer=None):
        if actor not in {"admin", "customer"}:
            raise ValueError("Unknown order action actor.")
        filters = {"id": order_id}
        if actor == "customer":
            filters["customer"] = customer
        order = self.order_model.objects.select_related("status").filter(**filters).first()
        if order is None:
            raise self.NotFoundError("Order not found.")
        assignments = self.status_action_model.objects.filter(
            order_status=order.status,
            **{f"order_action__{actor}": True},
        ).select_related("order_action", "order_action__set_status")
        return [
            self._action_payload(assignment)
            for assignment in assignments
            if assignment.order_action.code != "request_return"
            or self._return_eligible(order)
        ]

    @transaction.atomic
    def execute_action(self, order_id, action_code, *, actor, customer=None, admin=None):
        if actor not in {"admin", "customer"}:
            raise ValueError("Unknown order action actor.")
        if actor == "admin" and admin is None:
            raise ValueError("Admin actor requires an admin user.")
        filters = {"id": order_id}
        if actor == "customer":
            filters["customer"] = customer
        order = (
            self.order_model.objects.select_for_update()
            .select_related("status")
            .filter(**filters)
            .first()
        )
        if order is None:
            raise self.NotFoundError("Order not found.")
        assignment = (
            self.status_action_model.objects.select_related(
                "order_action", "order_action__set_status"
            )
            .filter(order_status=order.status, order_action__code=action_code)
            .first()
        )
        if assignment is None:
            raise self.ValidationError({
                "action": [_('This action is not available for the current order status.')]
            })
        action = assignment.order_action
        if action.code == "request_return":
            raise self.ValidationError({
                "action": [_('Create a return request through the returns endpoint.')]
            })
        if not getattr(action, actor):
            raise self.ValidationError({
                "action": [_('This actor is not allowed to execute the action.')]
            })

        tracked_before = {
            "status_id": order.status_id,
            "reservation_expires_at": (
                order.reservation_expires_at.isoformat()
                if order.reservation_expires_at is not None
                else None
            ),
        }
        update_fields = []
        if action.code == "cancel":
            self.release_reservations(order)
            # Restore consumed supply cost layers for finalized items.
            # Items whose FIFO consumption never happened reverse nothing.
            self.reverse_order_supply_consumption(order)
            if order.reservation_expires_at is not None:
                order.reservation_expires_at = None
                update_fields.append("reservation_expires_at")
        if action.set_status is not None and action.set_status_id != order.status_id:
            order.status = action.set_status
            update_fields.append("status")
        if update_fields:
            order.save(update_fields=[*update_fields, "updated_at"])
            tracked_after = {
                "status_id": order.status_id,
                "reservation_expires_at": (
                    order.reservation_expires_at.isoformat()
                    if order.reservation_expires_at is not None
                    else None
                ),
            }
            changed_fields = {
                field
                for field, before_value in tracked_before.items()
                if before_value != tracked_after[field]
            }
            if changed_fields:
                user = admin if actor == "admin" else customer
                self.history_model.objects.create(
                    order=order,
                    action=action,
                    user_id=user.pk if user is not None else None,
                    user_model=user._meta.label if user is not None else None,
                    before_values={
                        field: tracked_before[field] for field in changed_fields
                    },
                    after_values={
                        field: tracked_after[field] for field in changed_fields
                    },
                    description=(
                        f"Order action '{action.name}' executed by {actor}."
                    ),
                )
        return order

    def cancel_order(self, customer, order_id):
        return self.execute_action(
            order_id,
            "cancel",
            actor="customer",
            customer=customer,
        )

    # ───────────────────────── serialization ─────────────────────────

    def _status_actions_payload(self, order, *, actor):
        return [
            {
                "id": assignment.order_action.id,
                "code": assignment.order_action.code,
                "name": assignment.order_action.name,
                "fa_name": assignment.order_action.fa_name,
            }
            for assignment in order.status.status_actions.all()
            if getattr(assignment.order_action, actor)
            and (
                assignment.order_action.code != "request_return"
                or self._return_eligible(order)
            )
        ]
