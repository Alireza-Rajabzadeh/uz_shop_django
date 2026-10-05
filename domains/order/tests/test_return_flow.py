from datetime import datetime, timedelta

from django.utils import timezone

from domains.inventory.models import InventorySupply, InventorySupplyConsumption
from domains.order.models import (
    OrderAction,
    OrderHistory,
    OrderStatus,
    ReturnRequest,
)
from domains.order.return_flow import ReturnRequestService

from .test_checkout import CheckoutFixture


class ReturnFlowFixture(CheckoutFixture):
    """One delivered order whose line was already costed out of a supply."""

    def setUp(self):
        super().setUp()
        self.returns = ReturnRequestService()

    def delivered_order(self, quantity=2, *, delivered_days_ago=0):
        variant, _offer, _inventory = self.make_variant(self.make_product())
        self.filled_cart(variant, quantity=quantity)
        order = self.service.checkout_from_cart(self.customer)
        self.supply = InventorySupply.objects.create(
            variant=variant,
            warehouse=self.warehouse,
            quantity=10,
            remaining_quantity=10,
            unit_buy_price="40.00",
            supplied_at=timezone.make_aware(datetime(2026, 1, 10, 12, 0)),
            received_at=timezone.make_aware(datetime(2026, 1, 11, 12, 0)),
        )
        self.service.consume_reservations(order)
        order.status = OrderStatus.objects.get(id=300)
        order.reservation_expires_at = None
        order.save(update_fields=["status", "reservation_expires_at", "updated_at"])
        delivery = OrderHistory.objects.create(
            order=order,
            action=OrderAction.objects.get(code="deliver"),
            description="Delivered",
        )
        if delivered_days_ago:
            OrderHistory.objects.filter(pk=delivery.pk).update(
                created_at=timezone.now() - timedelta(days=delivered_days_ago)
            )
        return order

    def request_return(self, order, *, quantity=2):
        return self.returns.create(
            self.customer,
            order_id=order.id,
            reason="Broken on arrival",
            refund_destination_type="card",
            refund_destination_value="6037991234567890",
            items=[{"order_item_id": order.items.get().id, "quantity": quantity}],
        )


class ReturnEligibilityTests(ReturnFlowFixture):
    def test_a_delivered_order_inside_the_window_is_eligible(self):
        order = self.delivered_order()

        self.assertTrue(ReturnRequestService.is_eligible(order))

    def test_an_order_that_was_never_delivered_is_not_eligible(self):
        order = self.delivered_order()
        order.status = OrderStatus.objects.get(name="paid")
        order.save(update_fields=["status", "updated_at"])

        self.assertFalse(ReturnRequestService.is_eligible(order))

    def test_delivery_older_than_the_window_is_not_eligible(self):
        order = self.delivered_order(delivered_days_ago=4)

        self.assertFalse(ReturnRequestService.is_eligible(order))

    def test_delivery_time_comes_from_the_deliver_history_row(self):
        order = self.delivered_order()

        delivered_at = ReturnRequestService.delivery_time(order)

        self.assertIsNotNone(delivered_at)
        self.assertEqual(
            OrderHistory.objects.filter(order=order, action__code="deliver")
            .values_list("created_at", flat=True)
            .get(),
            delivered_at,
        )

    def test_an_open_request_closes_the_window_again(self):
        order = self.delivered_order()
        self.request_return(order)

        self.assertFalse(ReturnRequestService.is_eligible(order))

    def test_a_rejected_request_reopens_the_window(self):
        order = self.delivered_order()
        request = self.request_return(order)
        self.returns.execute_admin_action(
            order.id, request.id, "reject", admin_note="Salable"
        )
        request.refresh_from_db()

        self.assertEqual(request.status, "rejected")
        self.assertTrue(ReturnRequestService.is_eligible(order))


class ReturnCreationTests(ReturnFlowFixture):
    def test_creating_records_the_request_and_its_line(self):
        order = self.delivered_order(quantity=2)

        request = self.request_return(order)

        self.assertEqual(request.status, "requested")
        self.assertEqual(request.order, order)
        self.assertEqual(request.customer, self.customer)
        self.assertEqual(request.reason, "Broken on arrival")
        item = request.items.get()
        self.assertEqual(item.order_item_id, order.items.get().id)
        self.assertEqual(item.quantity, 2)

    def test_returning_more_than_was_sold_is_refused(self):
        order = self.delivered_order(quantity=2)

        with self.assertRaises(ReturnRequestService.ValidationError) as ctx:
            self.request_return(order, quantity=3)

        self.assertEqual(list(ctx.exception.errors), ["items"])
        self.assertEqual(self.returns.request_model.objects.count(), 0)

    def test_a_line_from_another_order_is_refused(self):
        order = self.delivered_order(quantity=2)
        other = self.delivered_order(quantity=1)

        with self.assertRaises(ReturnRequestService.ValidationError) as ctx:
            self.returns.create(
                self.customer,
                order_id=order.id,
                reason="Wrong item",
                refund_destination_type="card",
                refund_destination_value="6037991234567890",
                items=[
                    {"order_item_id": other.items.get().id, "quantity": 1}
                ],
            )

        self.assertEqual(list(ctx.exception.errors), ["items"])
        self.assertEqual(self.returns.request_model.objects.count(), 0)

    def test_an_ineligible_order_is_refused_before_anything_is_written(self):
        order = self.delivered_order(delivered_days_ago=4)

        with self.assertRaises(ReturnRequestService.ValidationError) as ctx:
            self.request_return(order)

        self.assertEqual(list(ctx.exception.errors), ["order_id"])
        self.assertEqual(self.returns.request_model.objects.count(), 0)

    def test_a_customer_only_sees_their_own_requests(self):
        order = self.delivered_order()
        created = self.request_return(order)

        self.assertEqual(list(self.returns.list(self.customer)), [created])
        with self.assertRaises(ReturnRequestService.NotFoundError):
            self.returns.get(self.customer, created.id + 999)


class ReturnDecisionTests(ReturnFlowFixture):
    def test_admin_actions_follow_the_current_status(self):
        order = self.delivered_order()
        request = self.request_return(order)
        self.assertEqual(
            self.returns.available_admin_actions(request.status),
            ["approve", "reject"],
        )

        self.returns.execute_admin_action(
            order.id, request.id, "approve", admin_note="Ok"
        )
        request.refresh_from_db()
        self.assertEqual(request.status, "approved")
        self.assertIsNotNone(request.approved_at)
        self.assertEqual(
            self.returns.available_admin_actions(request.status), ["received"]
        )

    def test_an_action_that_does_not_follow_is_refused(self):
        order = self.delivered_order()
        request = self.request_return(order)

        with self.assertRaises(ReturnRequestService.ValidationError) as ctx:
            self.returns.execute_admin_action(order.id, request.id, "complete")

        self.assertEqual(list(ctx.exception.errors), ["action"])
        request.refresh_from_db()
        self.assertEqual(request.status, "requested")

    def test_an_unknown_action_is_refused(self):
        order = self.delivered_order()
        request = self.request_return(order)

        with self.assertRaises(ReturnRequestService.ValidationError) as ctx:
            self.returns.execute_admin_action(order.id, request.id, "refund")

        self.assertEqual(list(ctx.exception.errors), ["action"])

    def test_a_request_from_another_order_is_not_reachable(self):
        order = self.delivered_order()
        request = self.request_return(order)
        other = self.delivered_order(quantity=1)

        with self.assertRaises(ReturnRequestService.NotFoundError):
            self.returns.execute_admin_action(
                other.id, request.id, "approve"
            )

    def test_completion_puts_the_cost_layers_back_exactly_as_they_came_out(self):
        order = self.delivered_order(quantity=2)
        request = self.request_return(order)
        self.returns.execute_admin_action(order.id, request.id, "approve")
        self.returns.execute_admin_action(order.id, request.id, "received")

        completed = self.returns.execute_admin_action(
            order.id, request.id, "complete"
        )

        self.assertEqual(completed.status, "completed")
        self.assertIsNotNone(completed.completed_at)
        consumption = InventorySupplyConsumption.objects.get()
        self.assertEqual(consumption.order_item, order.items.get())
        self.assertEqual(consumption.quantity, 2)
        self.assertEqual(consumption.reversed_quantity, 2)
        self.supply.refresh_from_db()
        self.assertEqual(self.supply.remaining_quantity, 10)

    def test_completion_twice_would_revisit_a_status_that_no_longer_matches(self):
        order = self.delivered_order()
        request = self.request_return(order)
        for action in ("approve", "received", "complete"):
            self.returns.execute_admin_action(order.id, request.id, action)

        with self.assertRaises(ReturnRequestService.ValidationError) as ctx:
            self.returns.execute_admin_action(order.id, request.id, "complete")

        self.assertEqual(list(ctx.exception.errors), ["action"])
        self.supply.refresh_from_db()
        self.assertEqual(self.supply.remaining_quantity, 10)

    def test_the_status_vocabulary_matches_the_model_s_choices(self):
        # The base writes its rules against literals so that both flows can
        # share them; this asserts the shop model still spells exactly them.
        status = ReturnRequest.Status
        self.assertEqual(
            ReturnRequestService.COUNTED_STATUSES,
            (
                status.REQUESTED,
                status.APPROVED,
                status.RECEIVED,
                status.COMPLETED,
            ),
        )
        self.assertEqual(
            ReturnRequestService.ACTIVE_STATUSES,
            (status.REQUESTED, status.APPROVED, status.RECEIVED),
        )


class ReturnPayloadTests(ReturnFlowFixture):
    def test_the_admin_payload_describes_the_request_its_lines_and_its_evidence(self):
        order = self.delivered_order()
        request = self.request_return(order)

        payload = self.returns.admin_payloads(order)[0]

        self.assertEqual(payload["id"], request.id)
        self.assertEqual(payload["status"], "requested")
        self.assertEqual(payload["customer"]["id"], self.customer.id)
        self.assertEqual(
            payload["refund_destination_masked"], "****7890"
        )
        self.assertEqual(
            [item["quantity"] for item in payload["items"]], [2]
        )
        self.assertEqual(payload["evidence"], [])
        self.assertEqual(payload["available_actions"], ["approve", "reject"])
