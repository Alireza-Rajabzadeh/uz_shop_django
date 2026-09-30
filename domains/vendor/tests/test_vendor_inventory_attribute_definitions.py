from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from domains.business.models import BusinessCategory, BusinessProfile
from domains.catalog.models import Category, CategoryStatus
from domains.inventory.models import InventoryAttributeDefinition
from domains.vendor.enums.VendorStatusEnum import VendorStatusEnum
from domains.vendor.models import Vendor, VendorStatus
from domains.vendor.views.inventory import VendorInventoryAttributeDefinitionsView


class VendorInventoryAttributeDefinitionsTests(TestCase):
    """The serialized-unit attribute vocabulary is two-scoped.

    Definitions are either global (``business IS NULL``, shared reference
    data) or owned by the business that inserted them because the attribute
    was missing. The list endpoint must return the globals plus the caller's
    own rows and never another business's rows; the create endpoint must only
    ever insert a row owned by the caller.
    """

    def setUp(self):
        self.factory = APIRequestFactory()

        self.vendor_status = VendorStatus.objects.create(
            id=VendorStatusEnum.ACTIVE.value, name="active", title="Active"
        )
        self.vendor = Vendor.objects.create_user(
            phone="09123334457",
            password="pass1234",
            first_name="Attribute",
            last_name="Vendor",
            national_id="1122334457",
            status=self.vendor_status,
        )
        self.other_vendor = Vendor.objects.create_user(
            phone="09123334458",
            password="pass1234",
            first_name="Other",
            last_name="Vendor",
            national_id="1122334458",
            status=self.vendor_status,
        )

        category_status = CategoryStatus.objects.create(name="active")
        category = Category.objects.create(name="Attribute Phones", status=category_status)
        self.business = BusinessProfile.objects.create(
            id=9997,
            vendor=self.vendor,
            business_name="Attribute Business",
            display_name="Attribute Business",
        )
        BusinessCategory.objects.create(business=self.business, category=category)
        self.other_business = BusinessProfile.objects.create(
            id=9996,
            vendor=self.other_vendor,
            business_name="Other Attribute Business",
            display_name="Other Attribute Business",
        )

        self.global_definition = InventoryAttributeDefinition.objects.create(
            business=None,
            name="IMEI",
            fa_title="شماره IMEI",
            code="imei",
            type="text",
        )
        self.own_definition = InventoryAttributeDefinition.objects.create(
            business=self.business,
            name="Box Serial",
            fa_title="شماره جعبه",
            code="box_serial",
            type="text",
        )
        self.foreign_definition = InventoryAttributeDefinition.objects.create(
            business=self.other_business,
            name="Other Secret",
            fa_title="عنوان دیگران",
            code="other_secret",
            type="text",
        )

    def _get(self):
        request = self.factory.get("/vendor/inventory/attribute-definitions")
        force_authenticate(request, user=self.vendor)
        return VendorInventoryAttributeDefinitionsView.as_view()(request)

    def _post(self, payload):
        request = self.factory.post(
            "/vendor/inventory/attribute-definitions", payload, format="json"
        )
        force_authenticate(request, user=self.vendor)
        return VendorInventoryAttributeDefinitionsView.as_view()(request)

    def test_list_returns_global_and_own_definitions(self):
        response = self._get()

        self.assertEqual(response.status_code, 200)
        rows = response.data["data"]
        self.assertEqual({row["code"] for row in rows}, {"imei", "box_serial"})

        by_code = {row["code"]: row for row in rows}
        self.assertTrue(by_code["imei"]["is_global"])
        self.assertEqual(by_code["imei"]["fa_title"], "شماره IMEI")
        self.assertFalse(by_code["box_serial"]["is_global"])
        self.assertEqual(by_code["box_serial"]["fa_title"], "شماره جعبه")

    def test_list_puts_global_definitions_first(self):
        response = self._get()

        self.assertEqual(response.status_code, 200)
        rows = response.data["data"]
        self.assertTrue(rows[0]["is_global"])

    def test_list_excludes_other_business_definitions(self):
        response = self._get()

        self.assertEqual(response.status_code, 200)
        codes = {row["code"] for row in response.data["data"]}
        self.assertNotIn("other_secret", codes)

    def test_insert_creates_a_definition_owned_by_the_caller(self):
        response = self._post({"name": "Warranty Card"})

        self.assertEqual(response.status_code, 201)
        row = response.data["data"]
        self.assertEqual(row["code"], "warranty_card")
        self.assertFalse(row["is_global"])
        self.assertEqual(row["fa_title"], "Warranty Card")
        self.assertEqual(row["type"], "text")

        definition = InventoryAttributeDefinition.objects.get(code="warranty_card")
        self.assertEqual(definition.business_id, self.business.id)
        self.assertIsNone(self.global_definition.business_id)

    def test_insert_accepts_an_explicit_fa_title_and_type(self):
        response = self._post({
            "name": "Activation Date",
            "fa_title": "تاریخ فعال‌سازی",
            "code": "Activation Date",
            "type": "date",
        })

        self.assertEqual(response.status_code, 201)
        definition = InventoryAttributeDefinition.objects.get(code="activation_date")
        self.assertEqual(definition.fa_title, "تاریخ فعال‌سازی")
        self.assertEqual(definition.type, "date")
        self.assertEqual(definition.business_id, self.business.id)

    def test_insert_rejects_a_code_that_already_exists_globally(self):
        response = self._post({"name": "IMEI"})

        self.assertEqual(response.status_code, 400)
        self.assertIn("already exists", str(response.data["errors"]))
        self.assertEqual(
            InventoryAttributeDefinition.objects.filter(code="imei").count(), 1
        )
        self.assertIsNone(self.global_definition.business_id)

    def test_insert_rejects_a_duplicate_of_an_own_definition(self):
        response = self._post({"name": "Box Serial"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            InventoryAttributeDefinition.objects.filter(code="box_serial").count(), 1
        )

    def test_insert_rejects_an_unsupported_type(self):
        response = self._post({"name": "Extras", "type": "json"})

        self.assertEqual(response.status_code, 400)
        self.assertFalse(
            InventoryAttributeDefinition.objects.filter(code="extras").exists()
        )

    def test_insert_rejects_a_name_that_yields_no_code(self):
        """A name of non-Latin characters cannot be turned into a code."""
        before = InventoryAttributeDefinition.objects.count()

        response = self._post({"name": "!!!"})

        self.assertEqual(response.status_code, 400)
        self.assertIn("code", str(response.data["errors"]))
        self.assertEqual(InventoryAttributeDefinition.objects.count(), before)

    def test_insert_ignores_a_code_owned_by_another_business(self):
        """A foreign code is invisible to this vendor, so it stays insertable."""
        response = self._post({"name": "Other Secret"})

        self.assertEqual(response.status_code, 201)
        definition = InventoryAttributeDefinition.objects.get(
            code="other_secret", business=self.business
        )
        self.assertIsNotNone(definition)
