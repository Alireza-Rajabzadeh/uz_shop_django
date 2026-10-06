"""The part of an order that is the same on either flow.

Expiring a reservation, moving an order to its next status and writing down
why are described once here. A marketplace order is not a shop order, but
"release the stock, set payment_expired, record that it timed out" is the
same sentence for both, so a flow supplies its tables and never restates a
transition.
"""

from django.db import transaction
from django.db.models import Q
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

    def _return_statuses(self):
        """The statuses that count as an open return, empty without returns."""
        service = self.return_service()
        return service.ACTIVE_STATUSES if service is not None else ()

    # ───────────────────────── scoping ─────────────────────────

    def _scoped_orders(self):
        """The order rows this instance may read or mutate.

        The customer flow narrows further by ``customer`` at each call site
        and the administrative flow deliberately narrows not at all. A flow
        that acts for someone who owns only part of the table — a seller
        working their own business — overrides this, so every read, action
        and status change below is scoped in the query instead of being
        checked afterwards by each caller.
        """
        return self.order_model.objects.all()

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
                    self._scoped_orders().select_for_update()
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
        order = self._scoped_orders().select_related("status").filter(**filters).first()
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
            self._scoped_orders().select_for_update()
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

    # ───────────────────────── reads ─────────────────────────

    def _get_customer_order(self, customer, order_id):
        try:
            return (
                self._scoped_orders().select_related("status")
                .prefetch_related("status__status_actions__order_action")
                .get(id=order_id, customer=customer)
            )
        except self.order_model.DoesNotExist as exc:
            raise self.NotFoundError("Order not found.") from exc

    def _expire_if_stale(self, order):
        if (
            order.status.name == self.STATUS_PAYMENT_PENDING
            and order.reservation_expires_at is not None
            and order.reservation_expires_at <= timezone.now()
        ):
            self.expire_orders([order])

    def get_order(self, customer, order_id):
        order = self._get_customer_order(customer, order_id)
        self._expire_if_stale(order)
        payload = self._customer_order_payload(order)
        payload["return_requests"] = [
            {
                "id": request.id,
                "status": request.status,
                "reason": request.reason,
                "customer_note": request.customer_note,
                "customer_response": request.customer_response,
                "refund_destination_type": request.refund_destination_type,
                "refund_destination_masked": f"****{request.refund_destination_value[-4:]}",
                "requested_at": request.requested_at.isoformat(),
                "approved_at": request.approved_at.isoformat() if request.approved_at else None,
                "received_at": request.received_at.isoformat() if request.received_at else None,
                "completed_at": request.completed_at.isoformat() if request.completed_at else None,
                "items": [
                    {
                        "order_item_id": item.order_item_id,
                        "quantity": item.quantity,
                        "reason": item.reason,
                    }
                    for item in request.items.all()
                ],
            }
            for request in self._returns_for(order=order, customer=customer)
        ]
        return payload

    def _returns_for(self, **filters):
        """This order flow's return rows, empty when the flow has no returns."""
        service = self.return_service()
        if service is None:
            return []
        return (
            service.request_model.objects.filter(**filters)
            .prefetch_related("items")
            .order_by("-requested_at", "-id")
        )

    def list_orders(self, customer):
        orders = list(
            self._scoped_orders().select_related("status")
            .filter(customer=customer)
            .prefetch_related(
                "items",
                "payments__payment_method",
                "status__status_actions__order_action",
            )
            .order_by("-created_at")
        )
        self.expire_lazy(orders)
        return [self._customer_order_payload(order) for order in orders]

    def list_orders_admin(self, *, include_returns=False, **filters):
        queryset = self._scoped_orders().select_related(
            "status", "customer"
        ).prefetch_related("status__status_actions__order_action")
        if include_returns:
            queryset = queryset.prefetch_related("return_requests")
        status = filters.get("status")
        if status:
            queryset = queryset.filter(status__name=status)
        if filters.get("in_progress"):
            queryset = queryset.filter(status__name__in=self.IN_PROGRESS_STATUSES)
        if filters.get("has_active_returns"):
            queryset = queryset.filter(
                return_requests__status__in=self._return_statuses()
            ).distinct()
        if filters.get("has_returns"):
            queryset = queryset.filter(
                return_requests__isnull=False
            ).distinct()
        state_id = filters.get("state_id")
        if state_id:
            queryset = queryset.filter(address_info__state_id=state_id)
        city_id = filters.get("city_id")
        if city_id:
            queryset = queryset.filter(address_info__city_id=city_id)
        search = (filters.get("search") or "").strip()
        if search:
            queryset = queryset.filter(
                Q(customer__phone__icontains=search)
                | Q(customer__first_name__icontains=search)
                | Q(customer__last_name__icontains=search)
            )
        created_from = filters.get("created_from")
        if created_from:
            queryset = queryset.filter(created_at__date__gte=created_from)
        created_to = filters.get("created_to")
        if created_to:
            queryset = queryset.filter(created_at__date__lte=created_to)
        ordering = (filters.get("ordering") or "").strip()
        if ordering in {"id", "-id", "created_at", "-created_at", "total_amount", "-total_amount"}:
            queryset = queryset.order_by(ordering, "id")
        else:
            queryset = queryset.order_by("-created_at", "id")
        return [
            self._admin_order_row(order, include_returns=include_returns)
            for order in queryset
        ]

    def _admin_order_row(self, order, *, include_returns=False):
        customer = order.customer
        payload = {
            "id": order.id,
            "customer": {
                "id": customer.id,
                "name": f"{customer.first_name} {customer.last_name}".strip(),
                "phone": customer.phone,
                "customer_code": customer.customer_code,
                "status": {
                    "id": customer.status.id,
                    "title": customer.status.title,
                    "is_active": customer.status.is_active,
                } if customer.status_id else None,
            },
            "status": {
                "id": order.status.id,
                "name": order.status.name,
                "fa_name": order.status.fa_name,
            },
            "available_actions": self._status_actions_payload(order, actor="admin"),
            "totals": {
                "subtotal": str(order.subtotal),
                "discount_amount": str(order.discount_amount),
                "shipping_amount": str(order.shipping_amount),
                "shipment": {
                    "original_price": str(order.shipping_original_amount),
                    "final_price": str(order.shipping_amount),
                },
                "total_amount": str(order.total_amount),
            },
            "reservation_expires_at": (
                order.reservation_expires_at.isoformat()
                if order.reservation_expires_at
                else None
            ),
            "created_at": order.created_at.isoformat(),
        }
        if include_returns:
            returns = sorted(
                order.return_requests.all(),
                key=lambda item: (item.requested_at, item.id),
                reverse=True,
            )
            open_statuses = self._return_statuses()
            payload["return_summary"] = {
                "count": len(returns),
                "open_count": sum(
                    request.status in open_statuses for request in returns
                ),
                "latest_status": returns[0].status if returns else None,
            }
        return payload

    def get_order_admin(self, order_id, *, include_returns=True):
        try:
            order = (
                self._scoped_orders().select_related("status", "customer__status")
                .prefetch_related("status__status_actions__order_action")
                .get(id=order_id)
            )
        except self.order_model.DoesNotExist as exc:
            raise self.NotFoundError("Order not found.") from exc
        payload = self._order_payload(order)
        payload["status"] = {
            "id": order.status.id,
            "name": order.status.name,
            "fa_name": order.status.fa_name,
        }
        payload["available_actions"] = self._status_actions_payload(
            order, actor="admin"
        )
        payload["customer"] = self._admin_order_row(order)["customer"]
        returns_service = self.return_service()
        if include_returns and returns_service is not None:
            payload["return_requests"] = returns_service().admin_payloads(order)
        payload["history"] = [
            {
                "id": entry.id,
                "action": {
                    "id": entry.action.id,
                    "code": entry.action.code,
                    "name": entry.action.name,
                    "fa_name": entry.action.fa_name,
                },
                "user_id": entry.user_id,
                "user_model": entry.user_model,
                "before_values": entry.before_values,
                "after_values": entry.after_values,
                "description": entry.description,
                "created_at": entry.created_at.isoformat(),
            }
            for entry in order.history.select_related("action").order_by(
                "-created_at", "-id"
            )
        ]
        return payload

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

    def _customer_order_payload(self, order):
        payload = self._order_payload(order)
        payload["status"] = {
            "id": order.status.id,
            "name": order.status.name,
            "fa_name": order.status.fa_name,
            "description": order.status.description,
        }
        payload["available_actions"] = self._status_actions_payload(
            order, actor="customer"
        )
        account_number = (
            order.successful_payment.resource_account_number
            if order.successful_payment is not None
            else None
        )
        payload["refund_destination_suggestion"] = (
            {
                "type": "card" if account_number.isdigit() and len(account_number) == 16 else "account",
                "value": account_number,
            }
            if account_number
            else None
        )
        return payload

    def _order_payload(self, order):
        item_rows = list(
            order.items.order_by("id")
        )
        thumbnails = self._product_thumbnails(
            [row.variant_info.get("product_id") for row in item_rows]
        )
        items = [
            {
                "id": item.id,
                "variant_id": item.variant_id,
                "sku": item.sku,
                "product_id": item.variant_info.get("product_id"),
                "product_name": item.variant_info.get("product_name"),
                "product_slug": item.variant_info.get("product_slug"),
                "product_image": (
                    item.variant_info.get("product_image")
                    or thumbnails.get(item.variant_info.get("product_id"))
                ),
                "combination_key": item.variant_info.get("combination_key"),
                "quantity": item.quantity,
                "unit_price": str(item.unit_price),
                "discount_type": item.discount_type,
                "discount_value": (
                    str(item.discount_value)
                    if item.discount_value is not None
                    else None
                ),
                "discount_amount": str(item.discount_amount),
                "final_price": str(item.final_price),
                "selections": item.variant_info.get("selections", []),
            }
            for item in item_rows
        ]
        payment = None
        if order.successful_payment is not None:
            successful_payment = order.successful_payment
            payment = {
                "id": successful_payment.id,
                "payment_method": successful_payment.payment_method.code,
                "payment_channel": (
                    successful_payment.payment_channel.code
                    if successful_payment.payment_channel
                    else None
                ),
                "amount": str(successful_payment.amount),
                "status": successful_payment.status,
                "ref_number": successful_payment.ref_number,
            }
        payments = [
            {
                "id": p.id,
                "payment_method": p.payment_method.code,
                "payment_method_name": p.payment_method.name,
                "payment_method_fa_name": p.payment_method.fa_name,
                "payment_channel": p.payment_channel.code if p.payment_channel else None,
                "payment_channel_name": p.payment_channel.name if p.payment_channel else None,
                "payment_channel_fa_name": p.payment_channel.fa_name if p.payment_channel else None,
                "channel_account_number": p.payment_channel.account_number if p.payment_channel else None,
                "channel_card_number": p.payment_channel.card_number if p.payment_channel else None,
                "status": p.status,
                "amount": str(p.amount),
                "ref_number": p.ref_number,
                "resource_account_number": p.resource_account_number,
                "documents": [
                    {
                        "id": document.id,
                        "file_id": str(document.file_id),
                        "original_name": document.file.original_name,
                        "content_type": document.file.content_type,
                        "url": file_url(document.file),
                    }
                    for document in p.documents.all()
                ],
            }
            for p in order.payments.select_related(
                "payment_method", "payment_channel"
            ).prefetch_related(
                "documents__file__status"
            ).order_by("id")
        ]
        return {
            "id": order.id,
            "status": order.status.name,
            "address_info": order.address_info,
            "items": items,
            "totals": {
                "subtotal": str(order.subtotal),
                "discount_amount": str(order.discount_amount),
                "shipping_amount": str(order.shipping_amount),
                "shipment": {
                    "original_price": str(order.shipping_original_amount),
                    "final_price": str(order.shipping_amount),
                },
                "total_amount": str(order.total_amount),
            },
            "reservation_expires_at": (
                order.reservation_expires_at.isoformat()
                if order.reservation_expires_at
                else None
            ),
            "successful_payment": payment,
            "payments": payments,
            "created_at": order.created_at.isoformat(),
        }


def file_url(file):
    """A URL for a stored file, or ``None`` when the provider refuses.

    Every flow's payloads link files the same way, and a dead link is worse
    than an absent one, so a provider failure is reported as "no URL" rather
    than raised at the reader.
    """
    from domains.files.services import FileService

    try:
        return FileService().url(file)
    except FileService.Error:
        return None
