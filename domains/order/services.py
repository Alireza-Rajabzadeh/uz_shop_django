from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import Count, F, Q as models_Q, Sum
from django.utils import timezone
from django.utils.translation import gettext as _

from domains.cart.services import CartService
from domains.catalog.models import ProductFile, ProductVariants
from domains.files.services import FileService
from domains.payments.services import PaymentService
from domains.shipment.services import ShipmentCalculationService
from domains.inventory.enums.SerializedStockStatusEnum import SerializedStockStatusEnum
from domains.inventory.models import SerializedStock, SerializedStockStatus, WarehouseStock
from domains.location.models import City, Country, State

from .models import (
    Order,
    OrderItem,
    OrderItemReservation,
    OrderHistory,
    OrderStatus,
    OrderStatusAction,
    ReturnRequest,
    ReturnRequestEvidence,
    ReturnRequestItem,
)


class OrderService:
    class ValidationError(Exception):
        def __init__(self, errors):
            self.errors = errors
            super().__init__(str(errors))

    class NotFoundError(Exception):
        pass

    STATUS_PAYMENT_PENDING = "payment_pending"
    STATUS_PAID = "paid"
    STATUS_PAYMENT_FAILED = "payment_failed"
    STATUS_CANCELLED = "cancelled"
    STATUS_PAYMENT_EXPIRED = "payment_expired"
    IN_PROGRESS_STATUSES = (
        STATUS_PAYMENT_PENDING,
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

    two_places = Decimal("0.01")
    shipment_service = ShipmentCalculationService()

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
            "product_slug": variant.product.slug,
            "product_image": self._product_thumbnails(
                [variant.product_id]
            ).get(variant.product_id),
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

    def _product_thumbnails(self, product_ids):
        ids = {pid for pid in product_ids if pid is not None}
        cache = getattr(self, "_thumbnail_urls", {})
        missing = sorted(ids - cache.keys())
        if missing:
            preferred = {}
            fallback = {}
            rows = (
                ProductFile.objects.filter(
                    product_id__in=missing,
                    role__in=[ProductFile.Role.THUMBNAIL, ProductFile.Role.GALLERY],
                )
                .select_related("file")
                .order_by("product_id", "position", "id")
            )
            file_service = FileService()
            for row in rows:
                if row.role == ProductFile.Role.THUMBNAIL:
                    preferred.setdefault(row.product_id, row)
                else:
                    fallback.setdefault(row.product_id, row)
            for product_id in missing:
                row = preferred.get(product_id) or fallback.get(product_id)
                url = None
                if row is not None:
                    try:
                        url = file_service.url(row.file)
                    except FileService.Error:
                        url = None
                cache[product_id] = url
            self._thumbnail_urls = cache
        return cache

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
        if not PaymentService.has_available_channel():
            raise self.ValidationError({
                "payment": [_("No active payment channel is available.")]
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

        status = self._status(self.STATUS_PAYMENT_PENDING)
        order = Order.objects.create(
            customer=customer,
            status=status,
            address_info=cart.address_info,
            subtotal=Decimal("0.00"),
            discount_amount=Decimal("0.00"),
            shipping_original_amount=Decimal("0.00"),
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
        shipment = self.shipment_service.calculate(order)
        order.shipping_original_amount = shipment.original_price
        order.shipping_amount = shipment.final_price
        order.total_amount = (
            subtotal - discount_total + shipment.final_price
        ).quantize(self.two_places)
        order.reservation_expires_at = timezone.now() + timedelta(
            minutes=settings.ORDER_RESERVATION_MINUTES
        )
        order.save(update_fields=[
            "subtotal",
            "discount_amount",
            "shipping_original_amount",
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
            return (
                Order.objects.select_related("status")
                .prefetch_related("status__status_actions__order_action")
                .get(id=order_id, customer=customer)
            )
        except Order.DoesNotExist as exc:
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
            for request in ReturnRequest.objects.filter(
                order=order, customer=customer
            ).prefetch_related("items").order_by("-requested_at", "-id")
        ]
        return payload

    def list_orders(self, customer):
        orders = list(
            Order.objects.select_related("status")
            .filter(customer=customer)
            .prefetch_related(
                "items__inventory_strategy",
                "payments__payment_method",
                "status__status_actions__order_action",
            )
            .order_by("-created_at")
        )
        self.expire_lazy(orders)
        return [self._customer_order_payload(order) for order in orders]

    def list_orders_admin(self, *, include_returns=False, **filters):
        queryset = Order.objects.select_related("status", "customer").prefetch_related(
            "status__status_actions__order_action"
        )
        if include_returns:
            queryset = queryset.prefetch_related("return_requests")
        status = filters.get("status")
        if status:
            queryset = queryset.filter(status__name=status)
        if filters.get("in_progress"):
            queryset = queryset.filter(status__name__in=self.IN_PROGRESS_STATUSES)
        if filters.get("has_active_returns"):
            queryset = queryset.filter(
                return_requests__status__in=ReturnRequestService.ACTIVE_STATUSES
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
            self._admin_order_row(order, include_returns=include_returns)
            for order in queryset
        ]

    def open_order_geography(self, **filters):
        queryset = Order.objects.all()
        if filters.get("in_progress"):
            queryset = queryset.filter(status__name__in=self.IN_PROGRESS_STATUSES)
        status = filters.get("status")
        if status:
            queryset = queryset.filter(status__name=status)
        if filters.get("has_active_returns"):
            queryset = queryset.filter(
                return_requests__status__in=ReturnRequestService.ACTIVE_STATUSES
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

        rows = (
            queryset.values(
                "address_info__state_id",
                "address_info__country_id",
                "address_info__state_name",
                "address_info__state_fa_title",
                "address_info__city_id",
                "address_info__city_name",
                "address_info__city_fa_title",
            )
            .annotate(order_count=Count("id"))
            .order_by()
        )
        total_open_orders = 0
        unmapped_order_count = 0
        province_data = {}
        city_ids = set()
        outside_iran_order_count = 0
        iran = Country.objects.filter(code="IR").only("id").first()
        current_states = list(
            State.objects.filter(country__code="IR").order_by("id")
        )
        iran_state_ids = {state.id for state in current_states}

        for row in rows:
            count = row["order_count"]
            total_open_orders += count
            state_id = self._positive_int(row["address_info__state_id"])
            city_id = self._positive_int(row["address_info__city_id"])
            country_id = self._positive_int(row["address_info__country_id"])
            is_iran = bool(
                iran
                and (
                    country_id == iran.id
                    or (country_id is None and state_id in iran_state_ids)
                )
            )
            if not is_iran or state_id is None or city_id is None:
                unmapped_order_count += count
                if iran and country_id is not None and country_id != iran.id:
                    outside_iran_order_count += count
                continue
            city_ids.add(city_id)
            province = province_data.setdefault(state_id, {
                "state_id": state_id,
                "name": row["address_info__state_name"] or "",
                "fa_title": row["address_info__state_fa_title"] or "",
                "order_count": 0,
                "cities": {},
            })
            province["order_count"] += count
            city = province["cities"].setdefault(city_id, {
                "city_id": city_id,
                "name": row["address_info__city_name"] or "",
                "fa_title": row["address_info__city_fa_title"] or "",
                "order_count": 0,
                "latitude": None,
                "longitude": None,
            })
            city["order_count"] += count

        locations = {
            city.id: city
            for city in City.objects.filter(id__in=city_ids).only(
                "id", "name", "fa_title", "latitude", "longitude"
            )
        }
        for province in province_data.values():
            for city in province["cities"].values():
                location = locations.get(city["city_id"])
                if location:
                    city["name"] = city["name"] or location.name
                    city["fa_title"] = city["fa_title"] or location.fa_title
                if (
                    location
                    and location.latitude is not None
                    and location.longitude is not None
                ):
                    city["latitude"] = float(location.latitude)
                    city["longitude"] = float(location.longitude)

        for state in current_states:
            province = province_data.setdefault(state.id, {
                "state_id": state.id,
                "name": state.name,
                "fa_title": state.fa_title,
                "order_count": 0,
                "cities": {},
            })
            province["name"] = province["name"] or state.name
            province["fa_title"] = province["fa_title"] or state.fa_title

        provinces = []
        city_without_coordinates_count = 0
        for province in province_data.values():
            cities = sorted(
                province.pop("cities").values(),
                key=lambda city: (-city["order_count"], city["city_id"]),
            )
            city_without_coordinates_count += sum(
                city["order_count"]
                for city in cities
                if city["latitude"] is None or city["longitude"] is None
            )
            province["cities"] = cities
            provinces.append(province)
        provinces.sort(
            key=lambda province: (-province["order_count"], province["state_id"])
        )
        mapped_order_count = total_open_orders - unmapped_order_count
        return {
            "total_open_orders": total_open_orders,
            "mapped_order_count": mapped_order_count,
            "unmapped_order_count": unmapped_order_count,
            "outside_iran_order_count": outside_iran_order_count,
            "city_without_coordinates_count": city_without_coordinates_count,
            "provinces": provinces,
        }

    @staticmethod
    def _positive_int(value):
        try:
            value = int(value)
        except (TypeError, ValueError):
            return None
        return value if value > 0 else None

    def _admin_order_row(self, order, *, include_returns=False):
        customer = order.customer
        payload = {
            "id": order.id,
            "customer": {
                "id": customer.id,
                "name": f"{customer.first_name} {customer.last_name}".strip(),
                "phone": customer.phone,
                "customer_code": customer.customer_code,
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
            payload["return_summary"] = {
                "count": len(returns),
                "open_count": sum(
                    request.status in ReturnRequestService.ACTIVE_STATUSES
                    for request in returns
                ),
                "latest_status": returns[0].status if returns else None,
            }
        return payload

    def get_order_admin(self, order_id, *, include_returns=True):
        try:
            order = (
                Order.objects.select_related("status", "customer")
                .prefetch_related("status__status_actions__order_action")
                .get(id=order_id)
            )
        except Order.DoesNotExist as exc:
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
        if include_returns:
            payload["return_requests"] = ReturnRequestService().admin_payloads(order)
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
                    Order.objects.select_for_update()
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

    def consume_reservations(self, order):
        """Convert an order's reserved stock into a sale."""
        from domains.inventory.services import InventorySupplyService

        supply_service = InventorySupplyService()
        sold_status = None
        for order_item in order.items.prefetch_related("reservations").select_related(
            "inventory_strategy"
        ):
            for reservation in order_item.reservations.all():
                if reservation.inventory_type == "warehouse_stock":
                    WarehouseStock.objects.filter(id=reservation.inventory_id).update(
                        reserved=F("reserved") - reservation.quantity,
                        sellable=F("sellable") - reservation.quantity,
                    )
                elif reservation.inventory_type == "serialized_stock":
                    if sold_status is None:
                        sold_status, _ = SerializedStockStatus.objects.get_or_create(
                            code="sold", defaults={"name": "sold"}
                        )
                    SerializedStock.objects.filter(id=reservation.inventory_id).update(
                        reserved=False,
                        sellable=False,
                        status_id=sold_status.id,
                    )
            # Finalized sale: consume FIFO cost layers for COGS tracking.
            # Runs inside the caller's transaction (payment approval).
            supply_service.consume_order_item(order_item)

    @staticmethod
    def reverse_order_supply_consumption(order):
        """Restore consumed cost layers for every item of a cancelled order."""
        from domains.inventory.services import InventorySupplyService

        supply_service = InventorySupplyService()
        for order_item in order.items.all():
            # Full reversal; items without consumption records are no-ops.
            supply_service.reverse_order_item_consumption(order_item)

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
        order = Order.objects.select_related("status").filter(**filters).first()
        if order is None:
            raise self.NotFoundError("Order not found.")
        assignments = OrderStatusAction.objects.filter(
            order_status=order.status,
            **{f"order_action__{actor}": True},
        ).select_related("order_action", "order_action__set_status")
        return [
            self._action_payload(assignment)
            for assignment in assignments
            if assignment.order_action.code != "request_return"
            or ReturnRequestService.is_eligible(order)
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
            Order.objects.select_for_update()
            .select_related("status")
            .filter(**filters)
            .first()
        )
        if order is None:
            raise self.NotFoundError("Order not found.")
        assignment = (
            OrderStatusAction.objects.select_related(
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
                OrderHistory.objects.create(
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

    @staticmethod
    def _status_actions_payload(order, *, actor):
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
                or ReturnRequestService.is_eligible(order)
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
            order.items.select_related("inventory_strategy").order_by("id")
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
                "inventory_strategy": {
                    "id": item.inventory_strategy_id,
                    "code": item.inventory_strategy.code,
                },
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
                        "url": self._file_url(document.file),
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

    @staticmethod
    def _file_url(file):
        from domains.files.services import FileService

        try:
            return FileService().url(file)
        except FileService.Error:
            return None


class ReturnRequestService:
    class ValidationError(Exception):
        def __init__(self, errors):
            self.errors = errors
            super().__init__(str(errors))

    class NotFoundError(Exception):
        pass

    COUNTED_STATUSES = (
        ReturnRequest.Status.REQUESTED,
        ReturnRequest.Status.APPROVED,
        ReturnRequest.Status.RECEIVED,
        ReturnRequest.Status.COMPLETED,
    )
    ACTIVE_STATUSES = (
        ReturnRequest.Status.REQUESTED,
        ReturnRequest.Status.APPROVED,
        ReturnRequest.Status.RECEIVED,
    )
    RETURN_WINDOW = timedelta(days=3)
    ACTION_TRANSITIONS = {
        "approve": (ReturnRequest.Status.REQUESTED, ReturnRequest.Status.APPROVED),
        "reject": (ReturnRequest.Status.REQUESTED, ReturnRequest.Status.REJECTED),
        "received": (ReturnRequest.Status.APPROVED, ReturnRequest.Status.RECEIVED),
        "complete": (ReturnRequest.Status.RECEIVED, ReturnRequest.Status.COMPLETED),
    }

    @classmethod
    def available_admin_actions(cls, status):
        return [
            action
            for action, (source, _target) in cls.ACTION_TRANSITIONS.items()
            if source == status
        ]

    def admin_payloads(self, order):
        requests = (
            ReturnRequest.objects.filter(order=order)
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
                    "url": OrderService._file_url(evidence.file),
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

    @transaction.atomic
    def execute_admin_action(
        self, order_id, return_request_id, action_code, *, admin_note=..., customer_response=...
    ):
        transition = self.ACTION_TRANSITIONS.get(action_code)
        if transition is None:
            raise self.ValidationError({"action": [_('Unknown return action.')]})
        request = (
            ReturnRequest.objects.select_for_update()
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
            ReturnRequest.Status.APPROVED: "approved_at",
            ReturnRequest.Status.RECEIVED: "received_at",
            ReturnRequest.Status.COMPLETED: "completed_at",
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
        if target == ReturnRequest.Status.COMPLETED:
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

    @classmethod
    def delivery_time(cls, order):
        return (
            OrderHistory.objects.filter(order=order, action__code="deliver")
            .order_by("-created_at", "-id")
            .values_list("created_at", flat=True)
            .first()
        )

    @classmethod
    def is_eligible(cls, order, *, now=None):
        if order.status.name != "delivered":
            return False
        if ReturnRequest.objects.filter(
            order=order,
            status__in=cls.ACTIVE_STATUSES,
        ).exists():
            return False
        delivered_at = cls.delivery_time(order)
        return bool(
            delivered_at
            and (now or timezone.now()) < delivered_at + cls.RETURN_WINDOW
        )

    @transaction.atomic
    def create(
        self, customer, *, order_id, reason, refund_destination_type,
        refund_destination_value, customer_note=None, items, images=None,
    ):
        try:
            order = (
                Order.objects.select_for_update()
                .select_related("status")
                .get(id=order_id, customer=customer)
            )
        except Order.DoesNotExist as exc:
            raise self.NotFoundError("Order not found.") from exc

        if not self.is_eligible(order):
            raise self.ValidationError({
                "order_id": [_('This order is not currently eligible for return.')]
            })

        requested_by_id = {item["order_item_id"]: item for item in items}
        order_items = list(
            OrderItem.objects.select_for_update()
            .filter(id__in=requested_by_id, order=order)
            .order_by("id")
        )
        if len(order_items) != len(requested_by_id):
            raise self.ValidationError({
                "items": [_('Every order item must belong to the selected order.')]
            })

        already_returned = {
            row["order_item_id"]: row["total"]
            for row in ReturnRequestItem.objects.filter(
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

        return_request = ReturnRequest.objects.create(
            order=order,
            customer=customer,
            reason=reason,
            customer_note=customer_note,
            refund_destination_type=refund_destination_type,
            refund_destination_value=refund_destination_value,
        )
        ReturnRequestItem.objects.bulk_create([
            ReturnRequestItem(
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
            ReturnRequestEvidence.objects.create(
                return_request=return_request,
                file=file,
                position=position,
            )
        return self.get(customer, return_request.id)

    @staticmethod
    def list(customer):
        return (
            ReturnRequest.objects.filter(customer=customer)
            .select_related("order")
            .prefetch_related("items", "evidence__file__status")
            .order_by("-requested_at", "-id")
        )

    @staticmethod
    def get(customer, return_request_id):
        try:
            return (
                ReturnRequest.objects.filter(customer=customer)
                .select_related("order")
                .prefetch_related("items", "evidence__file__status")
                .get(id=return_request_id)
            )
        except ReturnRequest.DoesNotExist as exc:
            raise ReturnRequestService.NotFoundError(
                "Return request not found."
            ) from exc
