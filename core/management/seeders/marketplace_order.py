from django.db import transaction

from core.management.seeders.base import BaseSeeder
from core.management.seeders.order import (
    ORDER_ACTIONS,
    ORDER_STATUSES,
    ORDER_STATUS_ACTIONS,
)
from domains.marketplace.models import (
    MarketplaceOrderAction,
    MarketplaceOrderStatus,
    MarketplaceOrderStatusAction,
)


class MarketplaceOrderSeeder(BaseSeeder):
    """Seed the marketplace status and action vocabulary.

    The rows are copied from the shop vocabulary in
    ``core/management/seeders/order.py`` rather than restated here, so the two
    flows cannot drift apart on what a status or an action means while still
    keeping separate tables they may later diverge on.
    """

    @transaction.atomic
    def run(self):
        self._seed_statuses()
        self._seed_actions()
        self._seed_status_actions()

    def _seed_statuses(self):
        status_ids = tuple(ORDER_STATUSES)
        # Free unique names before swapping canonical records between permanent IDs.
        for status in MarketplaceOrderStatus.objects.select_for_update().filter(
            id__in=status_ids
        ):
            status.name = f"__marketplace_order_status_seed_{status.id}__"
            status.save(update_fields=["name"])

        for status_id, (name, fa_name, description) in ORDER_STATUSES.items():
            MarketplaceOrderStatus.objects.update_or_create(
                id=status_id,
                defaults={
                    "name": name,
                    "fa_name": fa_name,
                    "description": description,
                },
            )

    def _seed_actions(self):
        action_ids = tuple(ORDER_ACTIONS)
        for action in MarketplaceOrderAction.objects.select_for_update().filter(
            id__in=action_ids
        ):
            action.code = f"__marketplace_order_action_seed_{action.id}__"
            action.save(update_fields=["code"])

        for action_id, (
            code,
            name,
            fa_name,
            admin,
            customer,
            status_id,
        ) in ORDER_ACTIONS.items():
            MarketplaceOrderAction.objects.update_or_create(
                id=action_id,
                defaults={
                    "code": code,
                    "name": name,
                    "fa_name": fa_name,
                    "admin": admin,
                    "customer": customer,
                    "set_status_id": status_id,
                },
            )

    def _seed_status_actions(self):
        for status_id, action_id in ORDER_STATUS_ACTIONS:
            MarketplaceOrderStatusAction.objects.get_or_create(
                order_status_id=status_id,
                order_action_id=action_id,
            )
