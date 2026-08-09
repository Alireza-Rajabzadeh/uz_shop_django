from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import F, Q as models_Q
from django.utils import timezone
from django.utils.translation import gettext as _

from domains.cart.services import CartService
from domains.catalog.models import ProductVariants
from domains.inventory.enums.SerializedStockStatusEnum import SerializedStockStatusEnum
from domains.inventory.models import SerializedStock, WarehouseStock

from .models import PAYMENT_SUCCESS
from .models import (
    Order,
    OrderItem,
    OrderItemReservation,
    OrderPayment,
    OrderPaymentChannel,
    OrderPaymentChannelSupportMethod,
    OrderPaymentMethod,
    OrderStatus,
)


class OrderService:
    class ValidationError(Exception):
        def __init__(self, errors):
            self.errors = errors
            super().__init__(str(errors))

    class NotFoundError(Exception):
        pass

    STATUS_PAYMENT_WAITING = "payment_waiting"
    STATUS_SUCCESS = "success"
    STATUS_FAILED = "failed"
    STATUS_EXPIRED = "expired"

    MANUAL_METHODS = ("card_to_card", "deposit_to_account")

    two_places = Decimal("0.01")

    # ───────────────────────── shared helpers ─────────────────────────

    def _status(self, name):
        return OrderStatus.objects.filter(name=name).first()

    def _line_snapshot(self, variant, quantity):
        price = variant.price.quantize(self.two_places)
        effective = self.cart_service().variant_service.calculate_discounted_price(
            variant
        ).quantize(self.two_places)
        unit_discount = max(price - effective, Decimal("0")).quantize(self.two_places)
        return {
            "unit_price": price,
            "discount_type": variant.discount_type,
            "discount_value": variant.discount_value,
            "unit_discount": unit_discount,
            "line_discount": (unit_discount * quantity).quantize(self.two_places),
            "line_total": (effective * quantity).quantize(self.two_places),
            "reservations": [],
        }

    def _variant_info_snapshot(self, variant):
        return {
            "variant_id": variant.id,
            "sku": variant.sku,
            "product_id": variant.product_id,
            "product_name": variant.product.name,
            "combination_key": variant.combination_key,
            "selections": [
                {
                    "attribute_id": selection.attribute_id,
                    "attribute": selection.attribute.name,
                    "option_id": selection.option_id,
                    "option": selection.option.name,
                }
                for selection in variant.selections.all()
            ],
        }

    @staticmethod
    def cart_service():
        return CartService()

    def _summary_map(self, variants):
        ids = [v.id for v in variants if v is not None]
        rows = ProductVariants.objects.filter(id__in=ids)
        rows = self.cart_service().inventory_service.annotate_variant_summaries(rows)
        return {row.id: row for row in rows}

    def _validate_item(self, item, summary):
        variant = item.variant
        if variant is None:
            return False, _("Item is no longer available.")
        product_status = variant.product.status.name.casefold()
        if product_status != "active":
            return False, _("Item %(sku)s is not available for purchase.") % {
                "sku": variant.sku
            }
        summary_row = summary.get(variant.id)
        available = summary_row.available_item_count if summary_row else 0
        if available < item.quantity:
            return False, _("Item %(sku)s does not have enough stock.") % {
                "sku": variant.sku
            }
        return True, ""

    # ───────────────────────── checkout ─────────────────────────

    @transaction.atomic
    def checkout_from_cart(self, customer):
        cart = self.cart_service().get_or_create_cart(customer)
        if not cart.address_info:
            raise self.ValidationError({
                "address": [_("Set a delivery address before checkout.")]
            })
        items = list(
            cart.items.select_related(
                "variant",
                "variant__product",
                "variant__inventory_strategy",
            )
            .prefetch_related(
                "variant__selections__attribute", "variant__selections__option"
            )
            .order_by("id")
        )
        if not items:
            raise self.ValidationError({"cart": [_("The cart is empty.")]})

        summary = self._summary_map([item.variant for item in items])
        validation_errors = []
        for item in items:
            ok, message = self._validate_item(item, summary)
            if not ok:
                validation_errors.append(message)
        if validation_errors:
            raise self.ValidationError({"items": validation_errors})

        status = self._status(self.STATUS_PAYMENT_WAITING)
        order = Order.objects.create(
            customer=customer,
            status=status,
            address_info=cart.address_info,
            subtotal=Decimal("0.00"),
            discount_amount=Decimal("0.00"),
            shipping_amount=Decimal("0.00"),
            total_amount=Decimal("0.00"),
        )
        subtotal = Decimal("0.00")
        discount_total = Decimal("0.00")
        for item in items:
            variant = item.variant
            line = self._line_snapshot(variant, item.quantity)
            self._reserve_return_item(variant, item.quantity, line["reservations"])
            order_item = OrderItem.objects.create(
                order=order,
                variant=variant,
                sku=variant.sku,
                quantity=item.quantity,
                unit_price=line["unit_price"],
                discount_type=line["discount_type"],
                discount_value=line["discount_value"],
                discount_amount=line["line_discount"],
                final_price=line["line_total"],
                inventory_strategy_id=variant.inventory_strategy_id,
                variant_info=self._variant_info_snapshot(variant),
            )
            for (inventory_type, inventory_id, quantity) in line["reservations"]:
                OrderItemReservation.objects.create(
                    order_item=order_item,
                    inventory_type=inventory_type,
                    inventory_id=inventory_id,
                    quantity=quantity,
                )
            subtotal += line["unit_price"] * item.quantity
            discount_total += line["line_discount"]

        order.subtotal = subtotal.quantize(self.two_places)
        order.discount_amount = discount_total.quantize(self.two_places)
        order.shipping_amount = Decimal("0.00")
        order.total_amount = (subtotal - discount_total).quantize(self.two_places)
        order.reservation_expires_at = timezone.now() + timedelta(
            minutes=settings.ORDER_RESERVATION_MINUTES
        )
        order.save(update_fields=[
            "subtotal",
            "discount_amount",
            "shipping_amount",
            "total_amount",
            "reservation_expires_at",
        ])
        for item in items:
            item.delete()
        return order

    def _reserve_return_item(self, variant, quantity, reservations):
        if variant.inventory_strategy.code == "normal":
            stock = (
                WarehouseStock.objects.select_for_update()
                .filter(variant=variant, warehouse__is_default=True)
                .first()
            )
            if stock is None:
                raise self.ValidationError({
                    "inventory": [_("No warehouse is configured for this item.")]
                })
            if stock.available < quantity:
                raise self.ValidationError({
                    "items": [
                        _("Item %(sku)s does not have enough stock.")
                        % {"sku": variant.sku}
                    ]
                })
            stock.reserved += quantity
            stock.save(update_fields=["reserved"])
            reservations.append(("warehouse_stock", stock.id, quantity))
        else:
            rows = list(
                SerializedStock.objects.select_for_update()
                .filter(
                    variant=variant,
                    status_id=SerializedStockStatusEnum.IN_STOCK.value,
                    sellable=True,
                    reserved=False,
                )
                .order_by("id")[: quantity]
            )
            if len(rows) < quantity:
                raise self.ValidationError({
                    "items": [
                        _("Item %(sku)s does not have enough stock.")
                        % {"sku": variant.sku}
                    ]
                })
            for row in rows:
                row.reserved = True
                row.save(update_fields=["reserved"])
                reservations.append(("serialized_stock", row.id, 1))

    # ───────────────────────── reads / expiry ─────────────────────────

    def _get_customer_order(self, customer, order_id):
        try:
            return Order.objects.select_related("status").get(
                id=order_id, customer=customer
            )
        except Order.DoesNotExist as exc:
            raise self.NotFoundError("Order not found.") from exc

    def _expire_if_stale(self, order):
        if (
            order.status.name == self.STATUS_PAYMENT_WAITING
            and order.reservation_expires_at is not None
            and order.reservation_expires_at <= timezone.now()
        ):
            self.expire_orders([order])

    def get_order(self, customer, order_id):
        order = self._get_customer_order(customer, order_id)
        self._expire_if_stale(order)
        return self._order_payload(order)

    def list_orders(self, customer):
        orders = list(
            Order.objects.select_related("status")
            .filter(customer=customer)
            .prefetch_related("items__inventory_strategy", "payments__payment_method")
            .order_by("-created_at")
        )
        self.expire_lazy(orders)
        return [self._order_payload(order) for order in orders]

    def list_orders_admin(self, **filters):
        queryset = Order.objects.select_related("status", "customer")
        status = filters.get("status")
        if status:
            queryset = queryset.filter(status__name=status)
        search = (filters.get("search") or "").strip()
        if search:
            queryset = queryset.filter(
                models_Q(customer__phone__icontains=search)
                | models_Q(customer__first_name__icontains=search)
                | models_Q(customer__last_name__icontains=search)
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
            self._admin_order_row(order)
            for order in queryset
        ]

    def _admin_order_row(self, order):
        customer = order.customer
        return {
            "id": order.id,
            "customer": {
                "id": customer.id,
                "name": f"{customer.first_name} {customer.last_name}".strip(),
                "phone": customer.phone,
                "customer_code": customer.customer_code,
            },
            "status": order.status.name,
            "status_fa_name": order.status.fa_name,
            "totals": {
                "subtotal": str(order.subtotal),
                "discount_amount": str(order.discount_amount),
                "shipping_amount": str(order.shipping_amount),
                "total_amount": str(order.total_amount),
            },
            "reservation_expires_at": (
                order.reservation_expires_at.isoformat()
                if order.reservation_expires_at
                else None
            ),
            "created_at": order.created_at.isoformat(),
        }

    def get_order_admin(self, order_id):
        try:
            order = Order.objects.select_related("status", "customer").get(id=order_id)
        except Order.DoesNotExist as exc:
            raise self.NotFoundError("Order not found.") from exc
        payload = self._order_payload(order)
        payload["customer"] = self._admin_order_row(order)["customer"]
        return payload

    def expire_lazy(self, orders):
        now = timezone.now()
        stale = [
            order
            for order in orders
            if order.status.name == self.STATUS_PAYMENT_WAITING
            and order.reservation_expires_at is not None
            and order.reservation_expires_at <= now
        ]
        if stale:
            self.expire_orders(stale)

    def expire_orders(self, orders=None):
        if orders is None:
            with transaction.atomic():
                orders = list(
                    Order.objects.select_for_update()
                    .select_related("status")
                    .filter(
                        status__name=self.STATUS_PAYMENT_WAITING,
                        reservation_expires_at__lte=timezone.now(),
                    )
                )
        if not orders:
            return []
        with transaction.atomic():
            expired = self._status(self.STATUS_EXPIRED)
            for order in orders:
                self._release_reservations(order)
                order.status = expired
                order.reservation_expires_at = None
                order.save(update_fields=["status", "reservation_expires_at"])
        return orders

    def _release_reservations(self, order):
        for order_item in order.items.prefetch_related("reservations"):
            for reservation in order_item.reservations.all():
                if reservation.inventory_type == "warehouse_stock":
                    WarehouseStock.objects.filter(id=reservation.inventory_id).update(
                        reserved=F("reserved") - reservation.quantity
                    )
                elif reservation.inventory_type == "serialized_stock":
                    SerializedStock.objects.filter(id=reservation.inventory_id).update(
                        reserved=False
                    )

    @transaction.atomic
    def cancel_order(self, customer, order_id):
        order = Order.objects.select_for_update().select_related("status").filter(
            id=order_id, customer=customer
        ).first()
        if order is None:
            raise self.NotFoundError("Order not found.")
        if order.status.name != self.STATUS_PAYMENT_WAITING:
            raise self.ValidationError({
                "order": [_("This order cannot be cancelled.")]
            })
        self._release_reservations(order)
        order.status = self._status(self.STATUS_FAILED)
        order.reservation_expires_at = None
        order.save(update_fields=["status", "reservation_expires_at"])
        return order

    # ───────────────────────── payments ─────────────────────────

    def payment_methods_payload(self):
        return [
            {
                "id": method.id,
                "name": method.name,
                "fa_name": method.fa_name,
                "channels": [
                    {
                        "id": support.payment_channel.id,
                        "name": support.payment_channel.name,
                        "fa_name": support.payment_channel.fa_name,
                        "account_number": support.payment_channel.account_number,
                        "card_number": support.payment_channel.card_number,
                        "owner_name": support.payment_channel.owner_name,
                    }
                    for support in method.supported_channels.select_related(
                        "payment_channel"
                    ).order_by("payment_channel_id")
                ],
            }
            for method in OrderPaymentMethod.objects.filter(available=True)
            .prefetch_related("supported_channels__payment_channel")
            .order_by("id")
        ]

    @transaction.atomic
    def confirm_manual_payment(
        self,
        customer,
        order_id,
        *,
        payment_method_name,
        payment_channel_id,
        ref_number=None,
        resource_account_number=None,
    ):
        order = (
            Order.objects.select_for_update().select_related("status")
            .filter(id=order_id, customer=customer)
            .first()
        )
        if order is None:
            raise self.NotFoundError("Order not found.")

        # Idempotent: a finalized order returns its current state.
        if order.status.name == self.STATUS_SUCCESS:
            return order
        if order.status.name == self.STATUS_EXPIRED:
            raise self.ValidationError({
                "order": [_("The order reservation has expired.")]
            })
        if order.status.name != self.STATUS_PAYMENT_WAITING:
            raise self.ValidationError({"order": [_("This order cannot be paid.")]})
        if payment_method_name not in self.MANUAL_METHODS:
            raise self.ValidationError({
                "payment_method": [
                    _("This payment method is not available for manual payment.")
                ]
            })

        method = OrderPaymentMethod.objects.filter(name=payment_method_name).first()
        if method is None or not method.available:
            raise self.ValidationError({
                "payment_method": [_("This payment method is not available.")]
            })
        channel = OrderPaymentChannel.objects.filter(id=payment_channel_id).first()
        if channel is None:
            raise self.ValidationError({
                "payment_channel": [_("This payment channel is not available.")]
            })
        if not OrderPaymentChannelSupportMethod.objects.filter(
            payment_channel=channel, payment_method=method
        ).exists():
            raise self.ValidationError({
                "payment_channel": [
                    _("This channel does not support the selected payment method.")
                ]
            })

        payment = OrderPayment.objects.create(
            order=order,
            payment_method=method,
            payment_channel=channel,
            amount=order.total_amount,
            status=PAYMENT_SUCCESS,
            ref_number=ref_number or "",
            resource_account_number=resource_account_number,
        )
        order.status = self._status(self.STATUS_SUCCESS)
        order.reservation_expires_at = None
        order.successful_payment = payment
        order.save(update_fields=[
            "status",
            "reservation_expires_at",
            "successful_payment",
        ])
        return order

    # ───────────────────────── serialization ─────────────────────────

    def _order_payload(self, order):
        items = [
            {
                "id": item.id,
                "variant_id": item.variant_id,
                "sku": item.sku,
                "product_id": item.variant_info.get("product_id"),
                "product_name": item.variant_info.get("product_name"),
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
                "inventory_strategy": {
                    "id": item.inventory_strategy_id,
                    "code": item.inventory_strategy.code,
                },
                "selections": item.variant_info.get("selections", []),
            }
            for item in order.items.select_related("inventory_strategy").order_by("id")
        ]
        payment = None
        if order.successful_payment is not None:
            successful_payment = order.successful_payment
            payment = {
                "id": successful_payment.id,
                "payment_method": successful_payment.payment_method.name,
                "payment_channel": (
                    successful_payment.payment_channel.name
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
                "payment_method": p.payment_method.name,
                "status": p.status,
                "amount": str(p.amount),
                "ref_number": p.ref_number,
            }
            for p in order.payments.select_related("payment_method").order_by("id")
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