from decimal import Decimal

from django.test import SimpleTestCase

from domains.shipment.services import ShipmentCalculationService


class ShipmentCalculationServiceTests(SimpleTestCase):
    def test_calculates_current_quote_for_cart_or_order_source(self):
        service = ShipmentCalculationService()

        for source in (object(), {"items": [], "address_info": {}}):
            with self.subTest(source=type(source).__name__):
                quote = service.calculate(source)
                self.assertEqual(quote.original_price, Decimal("200000.00"))
                self.assertEqual(quote.final_price, Decimal("0.00"))
