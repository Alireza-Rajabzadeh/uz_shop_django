from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from domains.business.models import (
    BusinessCharge,
    BusinessChargeCalculationType,
    BusinessChargeType,
    BusinessProfile,
)
from domains.business.services import BusinessChargeService
from domains.vendor.models import Vendor, VendorStatus


API_URL = "/api/vendor/business/charges"


def make_vendor(phone, national_id, status):
    return Vendor.objects.create(
        phone=phone,
        first_name="Charge",
        last_name="Owner",
        national_id=national_id,
        status=status,
    )


def make_business(vendor, name):
    return BusinessProfile.objects.create(
        vendor=vendor,
        business_name=name,
        display_name=name,
    )


class BusinessChargeFixtureMixin:
    @classmethod
    def setUpTestData(cls):
        status, _ = VendorStatus.objects.get_or_create(
            name="active", defaults={"title": "Active", "is_active": True}
        )
        cls.vendor = make_vendor("+989120000401", "9000000401", status)
        cls.business = make_business(cls.vendor, "Charge Seller")
        cls.other_vendor = make_vendor("+989120000402", "9000000402", status)
        cls.other_business = make_business(cls.other_vendor, "Other Seller")

    def make_charge(self, business=None, **overrides):
        values = {
            "business": business or self.business,
            "name": "VAT",
            "type": BusinessChargeType.TAX,
            "calculation_type": BusinessChargeCalculationType.FIXED,
            "amount": Decimal("9.5000"),
            "is_mandatory": True,
        }
        values.update(overrides)
        return BusinessCharge.objects.create(**values)


class BusinessChargeModelTests(BusinessChargeFixtureMixin, TestCase):
    def test_business_has_many_charges(self):
        first = self.make_charge(name="VAT")
        second = self.make_charge(
            name="Service fee",
            type=BusinessChargeType.EXTRA,
            calculation_type=BusinessChargeCalculationType.PERCENTAGE,
            amount=Decimal("2.5000"),
        )

        self.assertEqual(
            set(self.business.charges.values_list("id", flat=True)),
            {first.id, second.id},
        )

    def test_defaults(self):
        charge = self.make_charge()

        self.assertTrue(charge.is_active)
        self.assertTrue(charge.is_mandatory)
        self.assertEqual(charge.business_id, self.business.id)
        self.assertEqual(charge.type, "tax")
        self.assertEqual(charge.calculation_type, "fixed")

    def test_deleting_a_business_cascades_its_charges(self):
        charge = self.make_charge()

        self.business.delete()

        self.assertFalse(BusinessCharge.objects.filter(id=charge.id).exists())

    def test_negative_amount_is_rejected_by_the_database(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_charge(amount=Decimal("-0.0001"))

    def test_percentage_above_100_is_rejected_by_the_database(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_charge(
                calculation_type=BusinessChargeCalculationType.PERCENTAGE,
                amount=Decimal("100.0001"),
            )

    def test_fixed_amount_above_100_is_allowed(self):
        charge = self.make_charge(
            calculation_type=BusinessChargeCalculationType.FIXED,
            amount=Decimal("150.0000"),
        )

        self.assertEqual(charge.amount, Decimal("150.0000"))

    def test_service_percentage_rule(self):
        with self.assertRaises(BusinessChargeService.ValidationError):
            BusinessChargeService.validate_amount(
                BusinessChargeCalculationType.PERCENTAGE, Decimal("100.0001")
            )

        self.assertEqual(
            BusinessChargeService.validate_amount(
                BusinessChargeCalculationType.PERCENTAGE, Decimal("100.0000")
            ),
            Decimal("100.0000"),
        )


class BusinessChargeApiTests(BusinessChargeFixtureMixin, APITestCase):
    def setUp(self):
        self.authenticate(self.vendor)

    def authenticate(self, vendor):
        token = RefreshToken.for_user(vendor)
        token["user_type"] = "vendor"
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")

    def payload(self, **overrides):
        values = {
            "name": "VAT",
            "type": "tax",
            "calculation_type": "fixed",
            "amount": "9.5000",
            "is_mandatory": True,
        }
        values.update(overrides)
        return values

    def test_requires_authentication(self):
        self.client.credentials()

        self.assertEqual(self.client.get(API_URL).status_code, 401)
        self.assertEqual(
            self.client.post(API_URL, self.payload(), format="json").status_code,
            401,
        )

    def test_lists_only_the_callers_charges(self):
        own = self.make_charge(name="VAT")
        self.make_charge(self.other_business, name="Other VAT")

        response = self.client.get(API_URL)

        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["id"] for row in response.data["data"]], [own.id])

    def test_creates_a_charge_for_the_callers_business(self):
        response = self.client.post(
            API_URL,
            self.payload(
                type="extra",
                calculation_type="percentage",
                amount="4.2500",
                business_id=self.other_business.id,
            ),
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        data = response.data["data"]
        self.assertEqual(data["name"], "VAT")
        self.assertEqual(data["type"], "extra")
        self.assertEqual(data["calculation_type"], "percentage")
        self.assertEqual(data["amount"], "4.2500")
        charge = BusinessCharge.objects.get(id=data["id"])
        self.assertEqual(charge.business_id, self.business.id)
        self.assertTrue(charge.is_active)
        self.assertTrue(charge.is_mandatory)

    def test_retrieves_own_charge(self):
        charge = self.make_charge()

        response = self.client.get(f"{API_URL}/{charge.id}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["id"], charge.id)

    def test_updates_a_charge(self):
        charge = self.make_charge()

        response = self.client.patch(
            f"{API_URL}/{charge.id}",
            {"name": "Updated VAT", "amount": "12.0000", "is_mandatory": False},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.data["data"]
        self.assertEqual(data["name"], "Updated VAT")
        self.assertEqual(data["amount"], "12.0000")
        self.assertFalse(data["is_mandatory"])
        charge.refresh_from_db()
        self.assertEqual(charge.name, "Updated VAT")

    def test_deletes_a_charge(self):
        charge = self.make_charge()

        response = self.client.delete(f"{API_URL}/{charge.id}")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(BusinessCharge.objects.filter(id=charge.id).exists())

    def test_activates_and_deactivates_a_charge(self):
        charge = self.make_charge(is_active=False)

        activate = self.client.post(f"{API_URL}/{charge.id}/activate")
        self.assertEqual(activate.status_code, 200)
        self.assertTrue(activate.data["data"]["is_active"])
        charge.refresh_from_db()
        self.assertTrue(charge.is_active)

        deactivate = self.client.post(f"{API_URL}/{charge.id}/deactivate")
        self.assertEqual(deactivate.status_code, 200)
        self.assertFalse(deactivate.data["data"]["is_active"])
        charge.refresh_from_db()
        self.assertFalse(charge.is_active)

    def test_unknown_status_action_is_not_found(self):
        charge = self.make_charge()

        response = self.client.post(f"{API_URL}/{charge.id}/explode")

        self.assertEqual(response.status_code, 404)

    def test_rejects_an_unknown_type(self):
        response = self.client.post(
            API_URL, self.payload(type="discount"), format="json"
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("type", response.data["errors"])

    def test_rejects_an_unknown_calculation_type(self):
        response = self.client.post(
            API_URL, self.payload(calculation_type="tiered"), format="json"
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("calculation_type", response.data["errors"])

    def test_rejects_percentage_above_100(self):
        response = self.client.post(
            API_URL,
            self.payload(calculation_type="percentage", amount="100.0001"),
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("amount", response.data["errors"])

    def test_accepts_a_percentage_of_exactly_100(self):
        response = self.client.post(
            API_URL,
            self.payload(calculation_type="percentage", amount="100.0000"),
            format="json",
        )

        self.assertEqual(response.status_code, 201)

    def test_rejects_a_negative_amount(self):
        response = self.client.post(
            API_URL, self.payload(amount="-0.0001"), format="json"
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("amount", response.data["errors"])

    def test_update_rejects_a_percentage_above_100(self):
        charge = self.make_charge(
            calculation_type=BusinessChargeCalculationType.PERCENTAGE,
            amount=Decimal("10.0000"),
        )

        response = self.client.patch(
            f"{API_URL}/{charge.id}", {"amount": "100.5000"}, format="json"
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("amount", response.data["errors"])

    def test_switching_to_percentage_revalidates_the_stored_amount(self):
        charge = self.make_charge(
            calculation_type=BusinessChargeCalculationType.FIXED,
            amount=Decimal("150.0000"),
        )

        response = self.client.patch(
            f"{API_URL}/{charge.id}", {"calculation_type": "percentage"}, format="json"
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("amount", response.data["errors"])

    def test_another_business_charge_is_not_reachable(self):
        other = self.make_charge(self.other_business)

        self.assertEqual(
            self.client.get(f"{API_URL}/{other.id}").status_code, 404
        )
        self.assertEqual(
            self.client.patch(
                f"{API_URL}/{other.id}", {"name": "Hijacked"}, format="json"
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.delete(f"{API_URL}/{other.id}").status_code, 404
        )
        self.assertEqual(
            self.client.post(f"{API_URL}/{other.id}/deactivate").status_code, 404
        )
        other.refresh_from_db()
        self.assertTrue(other.is_active)
        self.assertEqual(other.name, "VAT")

    def test_a_vendor_without_a_business_gets_an_empty_list(self):
        vendor = make_vendor("+989120000403", "9000000403", self.vendor.status)
        self.authenticate(vendor)

        self.assertEqual(self.client.get(API_URL).data["data"], [])
        response = self.client.post(API_URL, self.payload(), format="json")
        self.assertEqual(response.status_code, 404)
