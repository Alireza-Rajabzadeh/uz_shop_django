from django.contrib.auth.models import User
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APIRequestFactory, force_authenticate

from django.test import TestCase

from domains.business.models import BusinessCategory, BusinessProfile
from domains.catalog.models import (
    Category,
    CategoryStatus,
    Product,
    ProductStatus,
    ProductVariantStatus,
    ProductVariants,
    VariantAttribute,
    VariantOption,
)
from domains.catalog.api.views import VariantDetailStatus
from domains.marketplace.models import BusinessOffer
from domains.vendor.enums.VendorStatusEnum import VendorStatusEnum
from domains.vendor.models import Vendor, VendorStatus
from domains.vendor.services.vendor_product_service import VendorProductService
from domains.vendor.views.inventory import VendorVariantPricingView
from domains.vendor.views.products import (
    VendorProductDetailView,
    VendorProductVariantDetailView,
    VendorProductVariantListCreateView,
    VendorVariantMarketplaceStatusView,
)


class VendorVariantConfirmationTests(TestCase):
    """A vendor-created variant waits for admin review before it is sold.

    While it waits the creator may still reshape it (that is the draft), but
    everything that would put it on sale — price, stock, supplies, marketplace
    listing — is refused by the backend, not merely hidden by the panel.
    """

    def setUp(self):
        self.factory = APIRequestFactory()

        self.vendor_status = VendorStatus.objects.create(
            id=VendorStatusEnum.ACTIVE.value, name="active", title="Active"
        )
        self.vendor = Vendor.objects.create_user(
            phone="09123334488",
            password="pass1234",
            first_name="Confirm",
            last_name="Vendor",
            national_id="1122334488",
            status=self.vendor_status,
        )

        category_status = CategoryStatus.objects.create(name="active")
        self.category = Category.objects.create(
            name="Confirmation Phones", status=category_status
        )
        self.business = BusinessProfile.objects.create(
            id=9996,
            vendor=self.vendor,
            business_name="Confirmation Business",
            display_name="Confirmation Business",
        )
        BusinessCategory.objects.create(business=self.business, category=self.category)

        self.product_status, _ = ProductStatus.objects.get_or_create(name="active")
        self.product = Product.objects.create(
            name="Confirmation Product", status=self.product_status
        )
        self.product.categories.add(self.category)

        self.variant_active, _ = ProductVariantStatus.objects.get_or_create(
            name="active"
        )
        self.variant_pending, _ = ProductVariantStatus.objects.get_or_create(
            name=VendorProductService.VARIANT_PENDING_STATUS
        )

        self.color = VariantAttribute.objects.create(name="Color")
        self.black = VariantOption.objects.create(
            attribute=self.color, name="Black", sku_code="BLK"
        )
        self.selections = [
            {"attribute_id": self.color.id, "option_id": self.black.id}
        ]

    # ─────────────────────── helpers ───────────────────────

    def _create_variant(self):
        request = self.factory.post(
            f"/vendor/products/{self.product.id}/variants",
            {"selections": self.selections},
            format="json",
        )
        force_authenticate(request, user=self.vendor)
        response = VendorProductVariantListCreateView.as_view()(
            request, product_id=self.product.id
        )
        self.assertEqual(response.status_code, 201, response.data)
        return response.data["data"]

    def _variant(self, variant_id):
        return ProductVariants.objects.select_related("status").get(pk=variant_id)

    def _list(self):
        request = self.factory.get(f"/vendor/products/{self.product.id}/variants")
        force_authenticate(request, user=self.vendor)
        return VendorProductVariantListCreateView.as_view()(
            request, product_id=self.product.id
        )

    def _detail_get(self, variant_id):
        request = self.factory.get(f"/vendor/variants/{variant_id}")
        force_authenticate(request, user=self.vendor)
        return VendorProductVariantDetailView.as_view()(
            request, variant_id=variant_id
        )

    def _detail_patch(self, variant_id, payload):
        request = self.factory.patch(
            f"/vendor/variants/{variant_id}", payload, format="json"
        )
        force_authenticate(request, user=self.vendor)
        return VendorProductVariantDetailView.as_view()(
            request, variant_id=variant_id
        )

    def _other_vendor(self):
        return Vendor.objects.create_user(
            phone="09123334499",
            password="pass1234",
            first_name="Other",
            last_name="Vendor",
            national_id="1122334499",
            status=self.vendor_status,
        )

    def _pending_variant_for(self, owner, sku):
        return ProductVariants.objects.create(
            product=self.product,
            status=self.variant_pending,
            sku=sku,
            combination_key=sku.lower(),
            created_by_vendor=owner,
            creator_model="vendor.vendor",
        )

    def _confirmed_variant(self, sku, owner=None):
        kwargs = {}
        if owner is not None:
            kwargs = {"created_by_vendor": owner, "creator_model": "vendor.vendor"}
        return ProductVariants.objects.create(
            product=self.product,
            status=self.variant_active,
            sku=sku,
            combination_key=sku.lower(),
            **kwargs,
        )

    def _listed_ids(self, response):
        return {row["id"] for row in response.data["data"]}

    # ─────────────────────── creation ───────────────────────

    def test_create_stamps_owner_and_pending_status(self):
        data = self._create_variant()

        variant = self._variant(data["id"])
        self.assertEqual(variant.created_by_vendor_id, self.vendor.pk)
        self.assertEqual(variant.creator_model, "vendor.vendor")
        self.assertEqual(variant.status.name, "wait_for_admin_confirmation")
        self.assertIsNone(variant.confirmed_by)
        self.assertTrue(data["editable"])

    # ─────────────────────── editability ───────────────────────

    def test_list_reports_editable_per_variant(self):
        created = self._create_variant()

        response = self._list()

        self.assertEqual(response.status_code, 200)
        rows = {row["id"]: row for row in response.data["data"]}
        self.assertTrue(rows[created["id"]]["editable"])

    def test_confirmed_variant_is_not_editable(self):
        created = self._create_variant()
        variant = self._variant(created["id"])
        variant.status = self.variant_active
        variant.save(update_fields=["status"])

        response = self._list()

        rows = {row["id"]: row for row in response.data["data"]}
        self.assertFalse(rows[created["id"]]["editable"])

    def test_editable_requires_the_creating_vendor(self):
        variant = ProductVariants.objects.create(
            product=self.product,
            status=self.variant_pending,
            sku="CONF-SKU-OTHER",
            combination_key="other",
            created_by_vendor=Vendor.objects.create_user(
                phone="09123334499",
                password="pass1234",
                first_name="Other",
                last_name="Vendor",
                national_id="1122334499",
                status=self.vendor_status,
            ),
            creator_model="vendor.vendor",
        )

        self.assertFalse(
            VendorProductService.can_vendor_edit_variant(variant, self.vendor)
        )

    def test_editable_requires_vendor_creator_model(self):
        variant = ProductVariants.objects.create(
            product=self.product,
            status=self.variant_pending,
            sku="CONF-SKU-CATALOG",
            combination_key="catalog",
            created_by_vendor=self.vendor,
            creator_model="catalog.product",
        )

        self.assertFalse(
            VendorProductService.can_vendor_edit_variant(variant, self.vendor)
        )

    def test_editable_requires_pending_status(self):
        variant = ProductVariants.objects.create(
            product=self.product,
            status=self.variant_active,
            sku="CONF-SKU-DONE",
            combination_key="done",
            created_by_vendor=self.vendor,
            creator_model="vendor.vendor",
        )

        self.assertFalse(
            VendorProductService.can_vendor_edit_variant(variant, self.vendor)
        )

    def test_admin_created_variants_have_no_owner_and_are_not_editable(self):
        variant = ProductVariants.objects.create(
            product=self.product,
            status=self.variant_active,
            sku="CONF-SKU-ADMIN",
            combination_key="admin",
        )

        self.assertFalse(
            VendorProductService.can_vendor_edit_variant(variant, self.vendor)
        )
        self.assertFalse(
            VendorProductService.is_variant_awaiting_confirmation(variant)
        )

    def test_variant_without_status_is_not_awaiting_confirmation(self):
        variant = ProductVariants.objects.create(
            product=self.product,
            sku="CONF-SKU-NOSTATUS",
            combination_key="nostatus",
        )

        self.assertFalse(
            VendorProductService.is_variant_awaiting_confirmation(variant)
        )
        # No status means no review state, and therefore nothing to manage:
        # level two only opens an own pending draft or an active row.
        with self.assertRaises(PermissionDenied):
            VendorProductService.assert_variant_manageable(variant)

    # ─────────────────────── detail reads ───────────────────────

    def test_detail_reports_editable_and_awaiting_confirmation(self):
        created = self._create_variant()

        response = self._detail_get(created["id"])

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["data"]["editable"])
        self.assertTrue(response.data["data"]["awaiting_confirmation"])

    def test_detail_stays_readable_while_awaiting_confirmation(self):
        created = self._create_variant()

        response = self._detail_get(created["id"])

        # The pending variant must remain visible; only writes are withheld.
        self.assertEqual(response.status_code, 200)

    # ─────────────────────── visibility across vendors ───────────────────────

    def test_list_hides_another_vendors_pending_variant(self):
        hidden = self._pending_variant_for(self._other_vendor(), "CONF-SKU-HIDE-1")

        response = self._list()

        self.assertEqual(response.status_code, 200)
        self.assertNotIn(hidden.id, self._listed_ids(response))

    def test_list_keeps_the_creators_own_pending_variant(self):
        created = self._create_variant()

        response = self._list()

        self.assertIn(created["id"], self._listed_ids(response))

    def test_list_shares_a_confirmed_variant_from_another_vendor(self):
        shared = self._confirmed_variant(
            "CONF-SKU-SHARE-1", owner=self._other_vendor()
        )

        response = self._list()

        self.assertIn(shared.id, self._listed_ids(response))

    def test_detail_read_hides_another_vendors_pending_variant(self):
        hidden = self._pending_variant_for(self._other_vendor(), "CONF-SKU-HIDE-2")

        response = self._detail_get(hidden.id)

        # Reported as missing, not forbidden: the id must not leak the draft.
        self.assertEqual(response.status_code, 404)

    def test_detail_patch_cannot_reach_another_vendors_pending_variant(self):
        hidden = self._pending_variant_for(self._other_vendor(), "CONF-SKU-HIDE-3")

        response = self._detail_patch(hidden.id, {"selections": self.selections})

        self.assertEqual(response.status_code, 404)

    def test_product_detail_scopes_variants_to_the_reader(self):
        other = self._other_vendor()
        hidden = self._pending_variant_for(other, "CONF-SKU-HIDE-4")
        shared = self._confirmed_variant("CONF-SKU-SHARE-2", owner=other)
        own = self._pending_variant_for(self.vendor, "CONF-SKU-OWN")

        request = self.factory.get(f"/vendor/products/{self.product.id}")
        force_authenticate(request, user=self.vendor)
        response = VendorProductDetailView.as_view()(request, id=self.product.id)

        self.assertEqual(response.status_code, 200, response.data)
        ids = {row["id"] for row in response.data["data"]["variants"]}
        self.assertNotIn(hidden.id, ids)
        self.assertIn(shared.id, ids)
        self.assertIn(own.id, ids)

    # ─────────────────────── level rules: product, then variant ───────────────────────

    def _set_product_status(self, name):
        self.product.status = ProductStatus.objects.get_or_create(name=name)[0]
        self.product.save(update_fields=["status"])

    def _post_variant(self):
        request = self.factory.post(
            f"/vendor/products/{self.product.id}/variants",
            {"selections": self.selections},
            format="json",
        )
        force_authenticate(request, user=self.vendor)
        return VendorProductVariantListCreateView.as_view()(
            request, product_id=self.product.id
        )

    def test_create_variant_requires_an_active_product(self):
        for name in ("inactive", "wait_for_admin_confirmation", "pending"):
            with self.subTest(product_status=name):
                self._set_product_status(name)
                self.assertEqual(self._post_variant().status_code, 403)
                self._set_product_status("active")

    def test_create_variant_is_allowed_on_an_active_product(self):
        response = self._post_variant()

        self.assertEqual(response.status_code, 201, response.data)

    def test_detail_patch_requires_an_active_product(self):
        created = self._create_variant()
        self._set_product_status("inactive")

        response = self._detail_patch(created["id"], {"selections": self.selections})

        self.assertEqual(response.status_code, 403)

    def test_detail_patch_refuses_an_inactive_variant(self):
        created = self._create_variant()
        ProductVariants.objects.filter(id=created["id"]).update(
            status=ProductVariantStatus.objects.get_or_create(name="inactive")[0]
        )

        response = self._detail_patch(created["id"], {"selections": self.selections})

        self.assertEqual(response.status_code, 403)

    def test_detail_patch_allows_an_active_variant(self):
        created = self._create_variant()
        ProductVariants.objects.filter(id=created["id"]).update(
            status=ProductVariantStatus.objects.get_or_create(name="active")[0]
        )

        response = self._detail_patch(created["id"], {"selections": self.selections})

        self.assertEqual(response.status_code, 200, response.data)

    def test_marketplace_listing_requires_an_active_product(self):
        variant = self._confirmed_variant("CONF-SKU-MKT", owner=self.vendor)
        self._set_product_status("inactive")

        request = self.factory.patch(
            f"/vendor/variants/{variant.id}/marketplace-status",
            {"is_active": True},
            format="json",
        )
        force_authenticate(request, user=self.vendor)
        response = VendorVariantMarketplaceStatusView.as_view()(
            request, variant_id=variant.id
        )

        self.assertEqual(response.status_code, 403)

    # ─────────────────────── writes while pending ───────────────────────

    def test_creator_may_still_edit_selections_while_pending(self):
        created = self._create_variant()

        response = self._detail_patch(
            created["id"], {"selections": self.selections}
        )

        self.assertEqual(response.status_code, 200, response.data)

    def test_price_is_refused_while_awaiting_confirmation(self):
        created = self._create_variant()

        response = self._detail_patch(created["id"], {"price": "150.00"})

        self.assertEqual(response.status_code, 403)
        self.assertIn(
            "waiting for admin confirmation", str(response.data)
        )
        self.assertFalse(
            BusinessOffer.objects.filter(variant_id=created["id"]).exists()
        )

    def test_inventory_is_refused_while_awaiting_confirmation(self):
        created = self._create_variant()

        response = self._detail_patch(
            created["id"], {"inventory": {"quantity": 10, "sellable": 8}}
        )

        self.assertEqual(response.status_code, 403)

    def test_pricing_configuration_is_refused_while_awaiting_confirmation(self):
        created = self._create_variant()

        request = self.factory.patch(
            f"/vendor/variants/{created['id']}/pricing",
            {"expected_profit_percentage": "10"},
            format="json",
        )
        force_authenticate(request, user=self.vendor)
        response = VendorVariantPricingView.as_view()(
            request, variant_id=created["id"]
        )

        self.assertEqual(response.status_code, 403)

    def test_marketplace_listing_is_refused_while_awaiting_confirmation(self):
        created = self._create_variant()

        request = self.factory.patch(
            f"/vendor/variants/{created['id']}/marketplace-status",
            {"is_active": True},
            format="json",
        )
        force_authenticate(request, user=self.vendor)
        response = VendorVariantMarketplaceStatusView.as_view()(
            request, variant_id=created["id"]
        )

        self.assertEqual(response.status_code, 403)

    def test_assert_variant_manageable_raises_only_for_pending_variants(self):
        pending = ProductVariants.objects.create(
            product=self.product,
            status=self.variant_pending,
            sku="CONF-SKU-GUARD",
            combination_key="guard",
        )
        confirmed = ProductVariants.objects.create(
            product=self.product,
            status=self.variant_active,
            sku="CONF-SKU-GUARD-2",
            combination_key="guard-2",
        )

        with self.assertRaises(PermissionDenied):
            VendorProductService.assert_variant_manageable(pending)
        VendorProductService.assert_variant_manageable(confirmed)

    # ─────────────────────── confirmation ───────────────────────

    def test_confirming_the_variant_records_the_admin_and_unlocks_price(self):
        created = self._create_variant()
        variant = self._variant(created["id"])
        admin = User.objects.create_superuser(
            username="variant-confirm-admin", password="password"
        )

        request = self.factory.patch(
            f"/catalog/variants/{variant.id}/status",
            {"status_id": self.variant_active.id},
            format="json",
        )
        force_authenticate(request, user=admin)
        response = VariantDetailStatus.as_view()(request, id=variant.id)

        self.assertEqual(response.status_code, 200, response.data)
        variant.refresh_from_db()
        self.assertEqual(variant.confirmed_by_id, admin.pk)
        self.assertEqual(variant.status_id, self.variant_active.id)

        # Definition locked, commerce unlocked.
        self.assertFalse(
            VendorProductService.can_vendor_edit_variant(variant, self.vendor)
        )
        self.assertFalse(
            VendorProductService.is_variant_awaiting_confirmation(variant)
        )
        patched = self._detail_patch(created["id"], {"price": "150.00"})
        self.assertEqual(patched.status_code, 200, patched.data)
        self.assertTrue(
            BusinessOffer.objects.filter(variant_id=created["id"]).exists()
        )
