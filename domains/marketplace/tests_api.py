"""The marketplace HTTP surface.

Both the customer routes and the admin routes are the shop's order views
with the flow swapped, so what is pinned here is that they answer from the
marketplace tables: an admin without ``marketplace.view_marketplaceorder``
is turned away, another customer's order is a 404, and a return created
over HTTP lands on a marketplace request rather than a shop one.

The seller's routes are here too because they read the same tables: they
scope by the caller's business, and they are where a manual payment is
finally decided.
"""

from django.contrib.auth.models import User
from rest_framework_simplejwt.tokens import RefreshToken

from domains.business.enums.BusinessStatusEnum import BusinessStatusEnum
from domains.business.models import BusinessProfile
from domains.customer.models import Customer
from domains.marketplace.models import (
    MarketplaceCart,
    MarketplaceOrder,
    MarketplaceOrderAction,
    MarketplaceOrderHistory,
    MarketplaceOrderPayment,
    MarketplaceOrderStatus,
    MarketplaceReturnRequest,
)
from domains.marketplace.services.payment_service import MarketplacePaymentService
from domains.order.models import ReturnRequest
from domains.vendor.models import Vendor, VendorStatus

from .tests_checkout import MarketplaceCheckoutFixture


def error_keys(response):
    """The field names a refusal blamed, whatever DEBUG wrapped them in."""
    errors = response.json()["errors"]
    if isinstance(errors, dict) and "details" in errors:
        errors = errors["details"]
    if isinstance(errors, dict):
        return set(errors)
    return {str(errors)}


class MarketplaceApiFixture(MarketplaceCheckoutFixture):
    def an_order(self, quantity=1):
        variant, _offer, _inventory = self.make_variant(self.make_product())
        self.filled_cart(variant, quantity=quantity)
        return self.service.checkout_from_cart(self.customer)

    def a_delivered_order(self, quantity=1):
        order = self.an_order(quantity)
        order.status = MarketplaceOrderStatus.objects.get(id=300)
        order.reservation_expires_at = None
        order.save(update_fields=["status", "reservation_expires_at", "updated_at"])
        MarketplaceOrderHistory.objects.create(
            order=order,
            action=MarketplaceOrderAction.objects.get(code="deliver"),
            description="Delivered",
        )
        return order

    def cancel_history(self, order):
        return [
            entry
            for entry in order.history.select_related("action")
            if entry.action.code == "cancel"
        ]


class MarketplaceCustomerApiTests(MarketplaceApiFixture):
    def test_the_order_routes_needs_a_customer(self):
        self.client.force_authenticate(user=None)

        response = self.client.get("/api/marketplace/orders")

        self.assertIn(response.status_code, (401, 403))

    def test_the_order_list_returns_only_this_customer_s_orders(self):
        order = self.an_order()
        other = Customer.objects.create_user(
            phone="09120000702",
            password="password",
            first_name="Other",
            last_name="Customer",
            customer_code="CUS-MKCO-002",
            status=self.customer.status,
        )

        self.client.force_authenticate(other)
        listing = self.client.get("/api/marketplace/orders")
        self.assertEqual(listing.json()["data"]["count"], 0)

        self.client.force_authenticate(self.customer)
        listing = self.client.get("/api/marketplace/orders")
        self.assertEqual(listing.json()["data"]["count"], 1)
        self.assertEqual(listing.json()["data"]["results"][0]["id"], order.id)

    def test_posting_an_order_checks_the_basket_out(self):
        variant, _offer, _inventory = self.make_variant(self.make_product())
        self.filled_cart(variant, quantity=2)
        self.client.force_authenticate(self.customer)

        response = self.client.post("/api/marketplace/orders", format="json")

        self.assertEqual(response.status_code, 201)
        payload = response.json()["data"]
        self.assertEqual(payload["items"][0]["quantity"], 2)
        self.assertEqual(payload["status"]["name"], "payment_pending")

    def test_posting_an_empty_basket_is_refused(self):
        # An addressed basket with nothing in it, so the refusal below is
        # about the emptiness rather than about a missing address.
        MarketplaceCart.objects.create(
            customer=self.customer, address_info={"city_name": "MkCi"}
        )
        self.client.force_authenticate(self.customer)

        response = self.client.post("/api/marketplace/orders", format="json")

        self.assertEqual(response.status_code, 400)
        self.assertIn("cart", error_keys(response))
        self.assertEqual(MarketplaceOrder.objects.count(), 0)

    def test_another_customer_s_order_is_not_readable(self):
        order = self.an_order()
        other = Customer.objects.create_user(
            phone="09120000703",
            password="password",
            first_name="Other",
            last_name="Customer",
            customer_code="CUS-MKCO-003",
            status=self.customer.status,
        )

        self.client.force_authenticate(other)

        self.assertEqual(
            self.client.get(f"/api/marketplace/orders/{order.id}").status_code, 404
        )
        self.assertEqual(
            self.client.get(
                f"/api/marketplace/orders/{order.id}/actions"
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                f"/api/marketplace/orders/{order.id}/actions/cancel"
            ).status_code,
            404,
        )

    def test_the_actions_endpoint_offers_cancel_and_the_action_endpoint_cancels(self):
        order = self.an_order()
        self.client.force_authenticate(self.customer)

        actions = self.client.get(f"/api/marketplace/orders/{order.id}/actions")
        self.assertEqual(
            [action["code"] for action in actions.json()["data"]["actions"]],
            ["cancel"],
        )

        response = self.client.post(
            f"/api/marketplace/orders/{order.id}/actions/cancel"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["status"]["name"], "cancelled")
        order.refresh_from_db()
        self.assertEqual(order.status.name, "cancelled")
        self.assertEqual(len(self.cancel_history(order)), 1)

    def test_cancelling_another_customer_s_order_is_refused(self):
        order = self.an_order()
        other = Customer.objects.create_user(
            phone="09120000704",
            password="password",
            first_name="Other",
            last_name="Customer",
            customer_code="CUS-MKCO-004",
            status=self.customer.status,
        )

        self.client.force_authenticate(other)
        response = self.client.post(
            f"/api/marketplace/orders/{order.id}/actions/cancel"
        )

        self.assertEqual(response.status_code, 404)

    def test_the_payment_methods_are_the_business_s_own(self):
        self.client.force_authenticate(self.customer)

        response = self.client.get("/api/marketplace/payment-methods")

        self.assertEqual(response.status_code, 200)
        methods = response.json()["data"]["methods"]
        self.assertIn("card_to_card", [method["code"] for method in methods])

    def test_a_return_can_be_created_listed_and_read_over_http(self):
        order = self.a_delivered_order()
        self.client.force_authenticate(self.customer)

        created = self.client.post(
            "/api/marketplace/returns",
            {
                "order_id": order.id,
                "reason": "Broken on arrival",
                "refund_destination_type": "card",
                "refund_destination_value": "6037991234567890",
                "items": [{"order_item_id": order.items.get().id, "quantity": 1}],
            },
            format="json",
        )

        self.assertEqual(created.status_code, 201)
        body = created.json()["data"]
        self.assertEqual(body["status"], "requested")
        self.assertEqual(MarketplaceReturnRequest.objects.count(), 1)
        # Nothing was written to the shop's return table.
        self.assertEqual(ReturnRequest.objects.count(), 0)

        listing = self.client.get("/api/marketplace/returns")
        self.assertEqual(listing.json()["data"]["count"], 1)

        detail = self.client.get(f"/api/marketplace/returns/{body['id']}")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["data"]["id"], body["id"])

    def test_an_order_outside_the_return_window_is_refused(self):
        order = self.an_order()
        self.client.force_authenticate(self.customer)

        response = self.client.post(
            "/api/marketplace/returns",
            {
                "order_id": order.id,
                "reason": "Too late",
                "refund_destination_type": "card",
                "refund_destination_value": "6037991234567890",
                "items": [{"order_item_id": order.items.get().id, "quantity": 1}],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("order_id", error_keys(response))
        self.assertEqual(MarketplaceReturnRequest.objects.count(), 0)


class MarketplaceAdminApiTests(MarketplaceApiFixture):
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_superuser("mk-admin", password="password")
        self.client.force_authenticate(self.admin)

    def test_the_admin_list_reads_marketplace_orders(self):
        order = self.an_order()

        response = self.client.get("/api/marketplace/admin/orders")

        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["count"], 1)
        row = data["results"][0]
        self.assertEqual(row["id"], order.id)
        self.assertEqual(row["status"]["name"], "payment_pending")
        self.assertEqual(row["customer"]["id"], self.customer.id)
        self.assertEqual(row["totals"]["total_amount"], str(order.total_amount))

    def test_the_admin_list_filters_by_status_and_returns(self):
        order = self.an_order()
        MarketplaceReturnRequest.objects.create(
            order=order,
            customer=self.customer,
            status="requested",
            reason="Broken",
            refund_destination_type="card",
            refund_destination_value="6037991234567890",
        )

        self.assertEqual(
            self.client.get(
                "/api/marketplace/admin/orders", {"status": "paid"}
            ).json()["data"]["count"],
            0,
        )
        self.assertEqual(
            self.client.get(
                "/api/marketplace/admin/orders", {"search": "Marketplace"}
            ).json()["data"]["count"],
            1,
        )
        self.assertEqual(
            self.client.get(
                "/api/marketplace/admin/orders", {"has_active_returns": "true"}
            ).json()["data"]["count"],
            1,
        )

    def test_the_admin_status_options_come_from_the_marketplace_table(self):
        MarketplaceOrderStatus.objects.create(
            id=999, name="mk_only", fa_name="فقط مارکت‌پلیس", description="Marketplace only"
        )

        response = self.client.get("/api/marketplace/admin/statuses")

        self.assertEqual(response.status_code, 200)
        names = [status["name"] for status in response.json()["data"]]
        self.assertIn("mk_only", names)

    def test_the_admin_detail_carries_actions_returns_and_history(self):
        order = self.a_delivered_order()

        response = self.client.get(f"/api/marketplace/admin/orders/{order.id}")

        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["status"]["name"], "delivered")
        self.assertEqual(data["customer"]["id"], self.customer.id)
        self.assertEqual(data["return_requests"], [])
        self.assertEqual(
            [entry["action"]["code"] for entry in data["history"]], ["deliver"]
        )

    def test_the_admin_can_execute_an_action(self):
        order = self.an_order()

        response = self.client.post(
            f"/api/marketplace/admin/orders/{order.id}/actions/cancel"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["status"]["name"], "cancelled")

    def test_the_admin_can_decide_on_a_return(self):
        order = self.a_delivered_order()
        request = MarketplaceReturnRequest.objects.create(
            order=order,
            customer=self.customer,
            status="requested",
            reason="Broken",
            refund_destination_type="card",
            refund_destination_value="6037991234567890",
        )

        response = self.client.post(
            f"/api/marketplace/admin/orders/{order.id}/returns/{request.id}/actions/approve",
            {"admin_note": "Accepted"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        request.refresh_from_db()
        self.assertEqual(request.status, "approved")
        self.assertIsNotNone(request.approved_at)
        self.assertEqual(request.admin_note, "Accepted")
        returned = response.json()["data"]["return_requests"][0]
        self.assertEqual(returned["id"], request.id)
        self.assertEqual(returned["status"], "approved")

    def test_an_admin_without_the_marketplace_order_permission_is_refused(self):
        self.client.force_authenticate(
            User.objects.create_user("mk-restricted", password="password")
        )

        for method, url in (
            ("get", "/api/marketplace/admin/orders"),
            ("get", "/api/marketplace/admin/orders/1"),
            ("post", "/api/marketplace/admin/orders/1/actions/cancel"),
        ):
            response = getattr(self.client, method)(url)
            self.assertEqual(response.status_code, 403, url)


class PaymentReviewFixture:
    """A manually paid marketplace order, and the two sides that read it.

    Both reviewers need the same unlikely setup: a checkout real enough to
    hold a stock hold, a payment the customer has submitted, and a seller
    whose token resolves to the business that owns it.
    """

    def setUp(self):
        super().setUp()
        # The inventory migration seeds a vendor-less profile at id=1, so the
        # checkout fixture's get_or_create keeps it and never attaches its
        # vendor. A seller token has to resolve one.
        self.business.vendor = Vendor.objects.get(vendor_code="VEN-MKCO-001")
        self.business.save(update_fields=["vendor"])

    def a_pending_payment(self):
        order = self.an_order()
        MarketplacePaymentService().confirm_manual_payment_for_customer(
            self.customer,
            order.id,
            payment_method_code="card_to_card",
            payment_channel_id=self.channel.id,
            ref_number="1234567890",
        )
        return order, MarketplaceOrderPayment.objects.get(order=order)

    def as_seller(self):
        self.client.force_authenticate(user=None)
        refresh = RefreshToken.for_user(self.business.vendor)
        refresh["user_type"] = "vendor"
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

    def action_codes(self, response):
        return [
            action["code"] for action in response.json()["data"]["available_actions"]
        ]

    def seller_action_codes(self, order_id):
        self.as_seller()
        response = self.client.get(f"/api/vendor/orders/{order_id}")
        self.assertEqual(response.status_code, 200)
        return self.action_codes(response)


class MarketplaceAdminPaymentReviewTests(PaymentReviewFixture, MarketplaceApiFixture):
    """Reviewing a manual payment is what opens the seller's order actions.

    A marketplace order only reaches ``paid`` through ``review_payment``, and a
    seller's first fulfillment step is offered from ``paid`` onward. These pin
    that the review is reachable over HTTP and that the seller's screen changes
    as a consequence — the alternative is an order stuck in
    ``payment_processing`` with no button on either side.
    """

    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_superuser(
            "mk-pay-admin", password="password"
        )
        self.client.force_authenticate(self.admin)

    def test_approving_pays_the_order(self):
        order, payment = self.a_pending_payment()

        response = self.client.post(
            f"/api/marketplace/admin/payments/{payment.id}/approve"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["status"]["name"], "paid")
        order.refresh_from_db()
        payment.refresh_from_db()
        self.assertEqual(order.status.name, "paid")
        self.assertEqual(payment.status.name, "successful")

    def test_an_approved_order_offers_the_seller_its_first_action(self):
        order, payment = self.a_pending_payment()
        self.client.post(f"/api/marketplace/admin/payments/{payment.id}/approve")

        self.assertEqual(self.seller_action_codes(order.id), ["confirm"])

    def test_rejecting_fails_the_payment_and_leaves_the_seller_waiting(self):
        order, payment = self.a_pending_payment()

        response = self.client.post(
            f"/api/marketplace/admin/payments/{payment.id}/reject"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["status"]["name"], "payment_failed")
        payment.refresh_from_db()
        self.assertEqual(payment.status.name, "failed")
        self.assertEqual(self.seller_action_codes(order.id), [])

    def test_a_payment_is_reviewed_only_once(self):
        _order, payment = self.a_pending_payment()
        self.client.post(f"/api/marketplace/admin/payments/{payment.id}/approve")

        response = self.client.post(
            f"/api/marketplace/admin/payments/{payment.id}/approve"
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(error_keys(response), {"payment"})

    def test_an_unknown_decision_is_not_found(self):
        _order, payment = self.a_pending_payment()

        response = self.client.post(
            f"/api/marketplace/admin/payments/{payment.id}/cancel"
        )

        self.assertEqual(response.status_code, 404)
        payment.refresh_from_db()
        self.assertEqual(payment.status.name, "pending")

    def test_reviewing_needs_the_marketplace_order_change_permission(self):
        _order, payment = self.a_pending_payment()
        self.client.force_authenticate(
            User.objects.create_user("mk-pay-restricted", password="password")
        )

        response = self.client.post(
            f"/api/marketplace/admin/payments/{payment.id}/approve"
        )

        self.assertEqual(response.status_code, 403)
        payment.refresh_from_db()
        self.assertEqual(payment.status.name, "pending")


class VendorOrderPaymentReviewTests(PaymentReviewFixture, MarketplaceApiFixture):
    """The seller decides whether a transfer to their own account landed.

    The payment reaches the seller's account, so nobody is better placed to
    confirm or reject it. What these pin is that the decision is scoped to the
    caller's business rather than to the payment id, and that it runs the
    review flow rather than the status action list — only the former moves the
    payment row and the stock hold along with the order.
    """

    def a_rival_seller(self):
        """Another confirmed store with its own token, for cross-business reads."""
        vendor = Vendor.objects.create(
            phone="+9990000091",
            first_name="Rival",
            last_name="Seller",
            national_id="0000000091",
            vendor_code="VEN-MKPAY-002",
            status=VendorStatus.objects.create(name="mkpay-active", title="Active"),
        )
        # An unconfirmed business is refused by the lifecycle middleware
        # before any route runs, which would prove scoping by the wrong door.
        business = BusinessProfile.objects.create(
            vendor=vendor,
            business_name="Rival Business",
            display_name="Rival Business",
            status_id=BusinessStatusEnum.ACTIVE.value,
        )
        return business, vendor

    def an_unpaid_order(self):
        """A second order of the seller's, with nothing submitted on it.

        Built directly: a customer holds one marketplace cart, so a second
        checkout from the same fixture would collide with the first.
        """
        return MarketplaceOrder.objects.create(
            customer=self.customer,
            business=self.business,
            status=MarketplaceOrderStatus.objects.get(name="payment_processing"),
            address_info={"city_name": "Tehran"},
            subtotal="100.00",
            discount_amount="0.00",
            shipping_original_amount="100.00",
            shipping_amount="0.00",
            total_amount="100.00",
        )

    def review(self, order_id, payment_id, decision="approve"):
        return self.client.post(
            f"/api/vendor/orders/{order_id}/payments/{payment_id}/{decision}",
            {},
            format="json",
        )

    def test_a_seller_approves_their_own_payment(self):
        order, payment = self.a_pending_payment()
        self.as_seller()

        response = self.review(order.id, payment.id)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["status"]["name"], "paid")
        # The same response is the seller's screen: approving pays the order
        # and hands the seller the fulfillment step that was missing.
        self.assertEqual(self.action_codes(response), ["confirm"])
        order.refresh_from_db()
        payment.refresh_from_db()
        self.assertEqual(order.status.name, "paid")
        self.assertEqual(payment.status.name, "successful")

    def test_the_approval_is_attributed_to_the_seller(self):
        order, payment = self.a_pending_payment()
        self.as_seller()
        self.review(order.id, payment.id)

        # Two entries now: the customer's submission and the seller's decision.
        entry = order.history.select_related("action").get(
            action__code="approve_payment"
        )
        self.assertEqual(entry.user_id, self.business.vendor_id)
        self.assertEqual(entry.user_model, "vendor.Vendor")

    def test_a_seller_rejects_their_own_payment(self):
        order, payment = self.a_pending_payment()
        self.as_seller()

        response = self.review(order.id, payment.id, "reject")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["status"]["name"], "payment_failed")
        self.assertEqual(self.action_codes(response), [])
        payment.refresh_from_db()
        self.assertEqual(payment.status.name, "failed")

    def test_another_sellers_payment_is_not_decidable(self):
        order, payment = self.a_pending_payment()
        _rival_business, rival_vendor = self.a_rival_seller()
        self.as_seller()
        # The rival owns nothing here, so the payment they target is absent
        # rather than forbidden — an id reveals nothing about someone else's
        # storefront.
        refresh = RefreshToken.for_user(rival_vendor)
        refresh["user_type"] = "vendor"
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

        response = self.review(order.id, payment.id)

        self.assertEqual(response.status_code, 404)
        payment.refresh_from_db()
        self.assertEqual(payment.status.name, "pending")

    def test_a_payment_is_decided_only_on_its_own_order(self):
        _order, payment = self.a_pending_payment()
        other_order = self.an_unpaid_order()
        self.as_seller()

        response = self.review(other_order.id, payment.id)

        self.assertEqual(response.status_code, 404)
        payment.refresh_from_db()
        self.assertEqual(payment.status.name, "pending")

    def test_a_reviewed_payment_is_not_reviewed_twice(self):
        order, payment = self.a_pending_payment()
        self.as_seller()
        self.review(order.id, payment.id)

        response = self.review(order.id, payment.id, "reject")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(error_keys(response), {"payment"})
        payment.refresh_from_db()
        self.assertEqual(payment.status.name, "successful")

    def test_an_unknown_decision_is_not_found(self):
        order, payment = self.a_pending_payment()
        self.as_seller()

        response = self.review(order.id, payment.id, "cancel")

        self.assertEqual(response.status_code, 404)
        payment.refresh_from_db()
        self.assertEqual(payment.status.name, "pending")

    def test_a_seller_cannot_use_the_action_list_for_it(self):
        # The seeded action table offers approve_payment to an admin actor at
        # this status, but executing it would only move the order's status.
        order, _payment = self.a_pending_payment()
        self.as_seller()

        response = self.client.post(
            f"/api/vendor/orders/{order.id}/actions/approve_payment", {}, format="json"
        )

        self.assertEqual(response.status_code, 400)
        order.refresh_from_db()
        self.assertEqual(order.status.name, "payment_processing")

    def test_reviewing_needs_a_seller(self):
        order, payment = self.a_pending_payment()
        self.client.force_authenticate(user=None)
        self.client.credentials()

        response = self.review(order.id, payment.id)

        self.assertIn(response.status_code, (401, 403))
        payment.refresh_from_db()
        self.assertEqual(payment.status.name, "pending")
