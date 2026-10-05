from django.db.models import Count, Q as models_Q

from domains.cart.services import CartService
from domains.payments.services import PaymentService
from domains.location.models import City, Country, State

from .flow import BaseOrderService
from .models import (
    Order,
    OrderItem,
    OrderItemReservation,
    OrderHistory,
    OrderStatus,
    OrderStatusAction,
)
from .return_flow import ReturnRequestService


class OrderService(BaseOrderService):
    """The shop flow: reads and administrative queries onto the shop tables.

    Checkout comes from ``domains.cart.checkout`` and the reservation
    lifecycle, status actions and audit history from ``domains.order.flow``.
    Everything declared here is what is genuinely shop-specific.
    """

    # The rows this flow writes.
    order_model = Order
    item_model = OrderItem
    reservation_model = OrderItemReservation
    status_model = OrderStatus
    status_action_model = OrderStatusAction
    history_model = OrderHistory

    @staticmethod
    def cart_service():
        return CartService()

    def return_service(self):
        return ReturnRequestService

    def _has_payment_channel(self):
        return PaymentService.has_available_channel()

    def _reservation_extra_fields(self, entry):
        """The shop hold table keeps the inventory labels the shared service drops."""
        return {
            "inventory_type": entry.inventory_type,
            "inventory_id": entry.inventory_id,
        }

    # ───────────────────────── administrative geography ─────────────────────────

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
