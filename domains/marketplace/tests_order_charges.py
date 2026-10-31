from decimal import Decimal
from unittest.mock import patch

from django.db import IntegrityError, transaction

from domains.business.models import BusinessCharge
from domains.marketplace.models import (
    MarketplaceOrder,
    MarketplaceOrderItemReservation,
    OrderCharge,
)
from domains.marketplace.services.charge_service import (
    MarketplaceOrderChargeService,
)
from domains.shipment.services import ShipmentPrice

from .tests_checkout import MarketplaceCheckoutFixture


class MarketplaceOrderChargeFixture(MarketplaceCheckoutFixture):
    def make_charge(self, **overrides):
        values = {
            "business": self.business,
            "name": "VAT",
            "type": "tax",
            "calculation_type": "fixed",
            "amount": Decimal("10.0000"),
            "is_active": True,
            "is_mandatory": False,
        }
        values.update(overrides)
        return BusinessCharge.objects.create(**values)

    def checkout(self, variant, quantity=1):
        self.filled_cart(variant, quantity=quantity)
        return self.service.checkout_business_from_cart(
            self.customer, self.business.id
        )


class MarketplaceOrderChargeTests(MarketplaceOrderChargeFixture):
    # ───────────────────────── creation ─────────────────────────

    def test_fixed_tax_charge_is_applied_to_the_order(self):
        variant, _offer, _inventory = self.make_variant(self.make_product())
        charge = self.make_charge(
            name="VAT", type="tax", calculation_type="fixed",
            amount=Decimal("15.0000"),
        )

        order = self.checkout(variant, quantity=2)

        self.assertEqual(order.subtotal, Decimal("200.00"))
        self.assertEqual(order.discount_amount, Decimal("0.00"))
        self.assertEqual(order.charges_total, Decimal("15.00"))
        self.assertEqual(order.total_amount, Decimal("215.00"))
        row = order.charges.get()
        self.assertEqual(row.business_charge_id, charge.id)
        self.assertEqual(row.name, "VAT")
        self.assertEqual(row.type, "tax")
        self.assertEqual(row.calculation_type, "fixed")
        self.assertEqual(row.rate, Decimal("15.0000"))
        self.assertEqual(row.amount, Decimal("15.00"))

    def test_fixed_extra_charge_is_applied_to_the_order(self):
        variant, _offer, _inventory = self.make_variant(self.make_product())
        self.make_charge(
            name="Service fee", type="extra", calculation_type="fixed",
            amount=Decimal("7.5000"),
        )

        order = self.checkout(variant, quantity=2)

        self.assertEqual(order.charges_total, Decimal("7.50"))
        self.assertEqual(order.total_amount, Decimal("207.50"))
        row = order.charges.get()
        self.assertEqual(row.type, "extra")
        self.assertEqual(row.amount, Decimal("7.50"))

    def test_percentage_charge_uses_the_discounted_subtotal(self):
        variant, _offer, _inventory = self.make_variant(
            self.make_product(),
            price="100.00",
            discount_type="percentage",
            discount_value=Decimal("10"),
        )
        self.make_charge(
            name="VAT", type="tax", calculation_type="percentage",
            amount=Decimal("9.5000"),
        )

        order = self.checkout(variant, quantity=2)

        # 2 x 100 = 200, 10% discount = 20, base = 180, 9.5% = 17.10.
        self.assertEqual(order.subtotal, Decimal("200.00"))
        self.assertEqual(order.discount_amount, Decimal("20.00"))
        self.assertEqual(order.charges_total, Decimal("17.10"))
        self.assertEqual(order.total_amount, Decimal("197.10"))
        self.assertEqual(order.charges.get().amount, Decimal("17.10"))

    def test_percentage_amount_is_decimal_not_float(self):
        variant, _offer, _inventory = self.make_variant(
            self.make_product(), price="99.99"
        )
        self.make_charge(
            name="VAT", calculation_type="percentage",
            amount=Decimal("8.2500"),
        )

        order = self.checkout(variant)

        # 99.99 * 8.25 / 100 = 8.249175 -> 8.25 at two places.
        self.assertEqual(order.charges_total, Decimal("8.25"))
        self.assertIsInstance(order.charges.get().amount, Decimal)

    def test_multiple_charges_are_all_applied(self):
        variant, _offer, _inventory = self.make_variant(self.make_product())
        first = self.make_charge(
            name="VAT", type="tax", calculation_type="fixed",
            amount=Decimal("10.0000"),
        )
        second = self.make_charge(
            name="Handling", type="extra", calculation_type="percentage",
            amount=Decimal("5.0000"),
        )

        order = self.checkout(variant, quantity=2)

        rows = list(order.charges.order_by("id"))
        self.assertEqual([row.business_charge_id for row in rows], [first.id, second.id])
        self.assertEqual(order.charges_total, Decimal("20.00"))
        self.assertEqual(order.total_amount, Decimal("220.00"))

    def test_inactive_charges_are_ignored(self):
        variant, _offer, _inventory = self.make_variant(self.make_product())
        self.make_charge(name="Retired", is_active=False)

        order = self.checkout(variant)

        self.assertEqual(order.charges.count(), 0)
        self.assertEqual(order.charges_total, Decimal("0.00"))
        self.assertEqual(order.total_amount, Decimal("100.00"))

    def test_an_order_without_configured_charges_has_zero_charges_total(self):
        variant, _offer, _inventory = self.make_variant(self.make_product())

        order = self.checkout(variant)

        self.assertEqual(order.charges_total, Decimal("0.00"))
        self.assertEqual(order.total_amount, Decimal("100.00"))

    # ───────────────────────── snapshots ─────────────────────────

    def test_a_later_configuration_change_does_not_move_the_order(self):
        variant, _offer, _inventory = self.make_variant(self.make_product())
        charge = self.make_charge(
            name="VAT", type="tax", calculation_type="fixed",
            amount=Decimal("10.0000"),
        )
        order = self.checkout(variant)

        charge.name = "Renamed"
        charge.type = "extra"
        charge.calculation_type = "percentage"
        charge.amount = Decimal("50.0000")
        charge.save()

        row = order.charges.get()
        self.assertEqual(row.name, "VAT")
        self.assertEqual(row.type, "tax")
        self.assertEqual(row.calculation_type, "fixed")
        self.assertEqual(row.rate, Decimal("10.0000"))
        self.assertEqual(row.amount, Decimal("10.00"))

        order.refresh_from_db()
        self.assertEqual(order.charges_total, Decimal("10.00"))
        self.assertEqual(order.total_amount, Decimal("110.00"))

    def test_deleting_a_configuration_keeps_the_snapshot(self):
        variant, _offer, _inventory = self.make_variant(self.make_product())
        charge = self.make_charge(
            name="VAT", calculation_type="fixed", amount=Decimal("10.0000")
        )
        order = self.checkout(variant)

        charge.delete()

        row = order.charges.get()
        self.assertIsNone(row.business_charge_id)
        self.assertEqual(row.name, "VAT")
        self.assertEqual(row.amount, Decimal("10.00"))
        order.refresh_from_db()
        self.assertEqual(order.charges_total, Decimal("10.00"))
        self.assertEqual(order.total_amount, Decimal("110.00"))

    # ───────────────────────── client input ─────────────────────────

    def test_a_client_cannot_submit_its_own_charge_amounts(self):
        self.client.force_authenticate(self.customer)
        variant, _offer, _inventory = self.make_variant(self.make_product())
        self.make_charge(
            name="VAT", calculation_type="fixed", amount=Decimal("10.0000")
        )
        self.filled_cart(variant, quantity=2)

        response = self.client.post(
            "/api/marketplace/orders/",
            {
                "business_id": self.business.id,
                "charges": [
                    {
                        "name": "Free stuff",
                        "type": "extra",
                        "calculation_type": "percentage",
                        "rate": "100.0000",
                        "amount": "999.00",
                    }
                ],
                "charges_total": "0.01",
                "total_amount": "0.01",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        order = MarketplaceOrder.objects.get(id=response.data["data"]["id"])
        self.assertEqual(order.charges_total, Decimal("10.00"))
        self.assertEqual(order.total_amount, Decimal("210.00"))
        self.assertEqual(
            list(order.charges.values_list("name", "amount")),
            [("VAT", Decimal("10.00"))],
        )
        self.assertEqual(
            response.data["data"]["totals"]["charges_total"], "10.00"
        )

    # ───────────────────────── atomicity ─────────────────────────

    def test_a_charge_failure_rolls_the_whole_checkout_back(self):
        variant, _offer, inventory = self.make_variant(self.make_product())
        self.make_charge()
        cart = self.filled_cart(variant, quantity=2)

        with patch.object(
            MarketplaceOrderChargeService,
            "apply",
            side_effect=RuntimeError("charge failure"),
        ):
            with self.assertRaises(RuntimeError):
                self.service.checkout_business_from_cart(
                    self.customer, self.business.id
                )

        self.assertEqual(MarketplaceOrder.objects.count(), 0)
        self.assertEqual(OrderCharge.objects.count(), 0)
        self.assertEqual(MarketplaceOrderItemReservation.objects.count(), 0)
        inventory.refresh_from_db()
        self.assertEqual(inventory.reserved, 0)
        self.assertEqual(inventory.sellable, 8)
        self.assertEqual(cart.items.count(), 1)

    # ───────────────────────── shipping separation ─────────────────────────

    def test_shipping_is_not_folded_into_order_charges(self):
        variant, _offer, _inventory = self.make_variant(self.make_product())
        self.make_charge(
            name="VAT", calculation_type="percentage",
            amount=Decimal("10.0000"),
        )

        with patch(
            "domains.shipment.services.ShipmentCalculationService.calculate",
            return_value=ShipmentPrice(
                original_price=Decimal("50000.00"),
                final_price=Decimal("50000.00"),
            ),
        ):
            order = self.checkout(variant)

        # 10% of the 100.00 subtotal, not of subtotal plus shipping.
        self.assertEqual(order.shipping_amount, Decimal("50000.00"))
        self.assertEqual(order.charges_total, Decimal("10.00"))
        self.assertEqual(order.total_amount, Decimal("50110.00"))
        self.assertEqual(order.charges.count(), 1)
        self.assertNotIn(
            "shipping", order.charges.values_list("name", flat=True)
        )


class OrderChargeModelTests(MarketplaceOrderChargeFixture):
    def test_order_charge_does_not_require_a_business_charge(self):
        variant, _offer, _inventory = self.make_variant(self.make_product())
        order = self.checkout(variant)
        row = OrderCharge.objects.create(
            order=order,
            business_charge=None,
            name="Historical",
            type="extra",
            calculation_type="fixed",
            rate=Decimal("10.0000"),
            amount=Decimal("10.00"),
        )

        self.assertIsNone(row.business_charge)
        self.assertEqual(order.charges.count(), 1)

    def test_negative_amount_is_rejected_by_the_database(self):
        variant, _offer, _inventory = self.make_variant(self.make_product())
        order = self.checkout(variant)

        with self.assertRaises(IntegrityError), transaction.atomic():
            OrderCharge.objects.create(
                order=order,
                name="Bad",
                type="extra",
                calculation_type="fixed",
                rate=Decimal("1.0000"),
                amount=Decimal("-0.01"),
            )
