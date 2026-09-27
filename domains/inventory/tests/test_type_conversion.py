from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from domains.business.models import BusinessProfile
from domains.catalog.models import (
    Category,
    CategoryStatus,
    Product,
    ProductStatus,
    ProductVariants,
    VariantAttribute,
    VariantOption,
)
from domains.inventory.enums.InventoryUnitStateEnum import InventoryUnitStateEnum
from domains.inventory.models import (
    Inventory,
    InventorySupply,
    InventoryUnit,
    Warehouse,
    WarehouseStatus,
)
from domains.inventory.services.inventory_service import InventoryService
from domains.location.models import City, Country, State
from domains.marketplace.models import BusinessOffer

STATE = InventoryUnitStateEnum


class InventoryTypeConversionTests(TestCase):
    def setUp(self):
        self.service = InventoryService()
        self.business, _ = BusinessProfile.objects.get_or_create(
            id=1,
            defaults={"business_name": "Conversion Business", "display_name": "Conversion"},
        )
        country = Country.objects.create(name="Conv Country", code="CV", phone_code="+1")
        state = State.objects.create(name="Conv State", country=country)
        city = City.objects.create(name="Conv City", state=state)
        self.warehouse_status = WarehouseStatus.objects.create(name="conv-available")
        self.warehouse = Warehouse.objects.create(
            code="WH-CONV",
            name="Conversion Warehouse",
            city=city,
            address="Address",
            lat="0",
            lng="0",
            is_default=True,
            status=self.warehouse_status,
        )
        category_status = CategoryStatus.objects.create(name="conv-active")
        product_status = ProductStatus.objects.create(name="conv-pending")
        category = Category.objects.create(name="Conv Category", status=category_status)
        self.product = Product.objects.create(name="Conv Product", status=product_status)
        self.product.categories.add(category)
        attribute = VariantAttribute.objects.create(name="Conv Color")
        option = VariantOption.objects.create(
            attribute=attribute, name="Black", sku_code="CONVBLK"
        )
        self.variant = ProductVariants.objects.create(
            product=self.product,
            sku="CONV-SKU-1",
            combination_key=f"{attribute.id}:{option.id}",
        )

    def _make_serialized_inventory(
        self, *, in_stock=0, reserved=0, sold=0, returned=0, changed_type=0
    ):
        inventory = Inventory.objects.create(
            business=self.business,
            warehouse=self.warehouse,
            variant=self.variant,
            inventory_type_id=2,
            quantity=0,
            sellable=0,
            reserved=0,
        )
        units = []
        for state, count in (
            (STATE.IN_STOCK.value, in_stock),
            (STATE.RESERVED.value, reserved),
            (STATE.SOLD.value, sold),
            (STATE.RETURNED.value, returned),
            (STATE.CHANGED_TYPE.value, changed_type),
        ):
            units.extend(
                InventoryUnit.objects.create(inventory=inventory, state=state)
                for _ in range(count)
            )
        self.service._sync_inventory_summary(inventory)
        inventory.refresh_from_db()
        return inventory, units

    def _make_normal_inventory(self, *, quantity=5, sellable=5, reserved=0):
        return Inventory.objects.create(
            business=self.business,
            warehouse=self.warehouse,
            variant=self.variant,
            inventory_type_id=1,
            quantity=quantity,
            sellable=sellable,
            reserved=reserved,
        )

    def _receive_supply(self, quantity):
        now = timezone.now()
        return InventorySupply.objects.create(
            business=self.business,
            warehouse=self.warehouse,
            variant=self.variant,
            quantity=quantity,
            unit_buy_price="100.00",
            supplied_at=now,
            received_at=now,
        )

    def _switch_to_normal(self):
        self.service.apply_variant_inventory(
            self.variant,
            inventory={"quantity": 0, "sellable": 0},
            serial_items=None,
            inventory_submitted=True,
            business=self.business,
        )

    def _inventory_type(self):
        return self.service.get_variant_details(
            self.variant, business=self.business
        )["inventory_type"]["code"]

    # ─────────────────────── serialized → normal ───────────────────────

    def test_serialized_to_normal_converts_live_units_to_changed_type(self):
        inventory, _ = self._make_serialized_inventory(
            in_stock=2, reserved=1, sold=1
        )
        self._receive_supply(quantity=10)

        self._switch_to_normal()

        states = set(
            InventoryUnit.objects.filter(inventory=inventory)
            .values_list("state", flat=True)
        )
        # live units become changed_type; sold history keeps its state
        self.assertEqual(
            states, {STATE.CHANGED_TYPE.value, STATE.SOLD.value}
        )
        inventory.refresh_from_db()
        self.assertEqual(inventory.inventory_type_id, 1)
        # available = sellable - reserved must survive the conversion
        self.assertEqual(inventory.sellable, 3)
        self.assertEqual(inventory.reserved, 1)
        self.assertEqual(inventory.quantity, 10)
        self.assertEqual(self._inventory_type(), "normal")

    def test_serialized_to_normal_requires_received_supplies(self):
        inventory, _ = self._make_serialized_inventory(in_stock=2)

        with self.assertRaises(InventoryService.ValidationError) as ctx:
            self._switch_to_normal()

        self.assertIn("Receive supplies before converting", str(ctx.exception))
        inventory.refresh_from_db()
        self.assertEqual(inventory.inventory_type_id, 2)
        self.assertEqual(self._inventory_type(), "serialized")

    def test_active_offer_blocks_inventory_type_change(self):
        self._make_serialized_inventory(in_stock=1)
        self._receive_supply(quantity=5)
        BusinessOffer.objects.create(
            business=self.business,
            variant=self.variant,
            price="100.00",
            is_active=True,
        )

        with self.assertRaises(InventoryService.ValidationError) as ctx:
            self._switch_to_normal()

        self.assertIn("Deactivate the marketplace offer", str(ctx.exception))

    def test_deactivated_offer_opens_inventory_type_change(self):
        self._make_serialized_inventory(in_stock=1)
        self._receive_supply(quantity=5)
        BusinessOffer.objects.create(
            business=self.business,
            variant=self.variant,
            price="100.00",
            is_active=False,
        )

        allowed, reason = self.service.inventory_type_change_gate(
            self.variant, self.business
        )
        self.assertTrue(allowed)
        self.assertIsNone(reason)
        self._switch_to_normal()
        self.assertEqual(self._inventory_type(), "normal")

    # ─────────────────────── normal → serialized ───────────────────────

    def test_normal_to_serialized_creates_units(self):
        self._make_normal_inventory(quantity=5, sellable=5)

        self.service.apply_variant_inventory(
            self.variant,
            inventory=None,
            serial_items=[
                {"serial_number": "SN-1", "on_sale": True},
                {"serial_number": "SN-2", "on_sale": False},
            ],
            inventory_submitted=True,
            business=self.business,
        )

        inventory = Inventory.objects.get(variant=self.variant)
        self.assertEqual(inventory.inventory_type_id, 2)
        self.assertEqual(
            InventoryUnit.objects.filter(
                inventory=inventory, state=STATE.IN_STOCK.value
            ).count(),
            1,
        )
        self.assertEqual(
            InventoryUnit.objects.filter(
                inventory=inventory, state=STATE.RESERVED.value
            ).count(),
            1,
        )
        self.assertEqual(self._inventory_type(), "serialized")

    # ─────────────────────── historical rows ───────────────────────

    def test_historical_units_do_not_block_a_serialized_save(self):
        inventory, units = self._make_serialized_inventory(
            in_stock=1, sold=1, returned=1
        )
        live, sold = units[0], units[1]

        self.service.apply_variant_inventory(
            self.variant,
            inventory=None,
            serial_items=[
                {"id": live.id, "serial_number": "SN-LIVE", "on_sale": False},
                {"id": sold.id, "serial_number": "SN-SOLD", "on_sale": False},
            ],
            inventory_submitted=True,
            business=self.business,
        )

        sold.refresh_from_db()
        live.refresh_from_db()
        self.assertEqual(sold.state, STATE.SOLD.value)
        self.assertEqual(live.state, STATE.RESERVED.value)
        # the unsubmitted historical row is history, not a deletion
        self.assertTrue(
            InventoryUnit.objects.filter(
                inventory=inventory, state=STATE.RETURNED.value
            ).exists()
        )

    def test_changed_type_is_not_counted_as_stock(self):
        self._make_serialized_inventory(in_stock=2, changed_type=3)

        summary = self.service.get_summary(self.variant, business=self.business)
        self.assertEqual(summary["total_item_count"], 2)
        self.assertEqual(summary["sellable_item_count"], 2)

        details = self.service.get_variant_details(self.variant, business=self.business)
        self.assertEqual(len(details["serial_items"]), 2)

    def test_converted_inventory_receives_normal_stock(self):
        inventory, _ = self._make_serialized_inventory(in_stock=1)
        self._receive_supply(quantity=4)
        self._switch_to_normal()

        updated = self.service.increase_stock(inventory.id, 2)

        self.assertEqual(updated.quantity, 6)
        self.assertEqual(updated.sellable, 3)

    # ─────────────────────── purge ───────────────────────

    def test_purge_only_removes_expired_changed_type_units(self):
        inventory, units = self._make_serialized_inventory(
            in_stock=1, changed_type=2
        )
        live, stale, fresh = units[0], units[1], units[2]
        InventoryUnit.objects.filter(pk=stale.pk).update(
            updated_at=timezone.now() - timedelta(days=120)
        )

        self.assertEqual(
            self.service.purge_changed_type_units(older_than_days=90, dry_run=True), 1
        )
        deleted = self.service.purge_changed_type_units(older_than_days=90)
        self.assertEqual(deleted, 1)

        remaining = set(
            InventoryUnit.objects.filter(inventory=inventory)
            .values_list("id", flat=True)
        )
        self.assertNotIn(stale.pk, remaining)
        self.assertIn(fresh.pk, remaining)
        self.assertIn(live.pk, remaining)

    # ─────────────────────── refresh ───────────────────────

    def test_refresh_on_serialized_counts_units_instead_of_raising(self):
        """Refresh re-derives serialized stock rather than rejecting it.

        The variant's units are the ledger for serialized inventory, so a
        refresh recounts them; it is not a supplies operation and must not
        fail as one.
        """
        inventory, _ = self._make_serialized_inventory(
            in_stock=2, reserved=1, sold=1, changed_type=3
        )
        # Drift the stored summary away from its units.
        Inventory.objects.filter(pk=inventory.pk).update(quantity=99, sellable=99)

        self.service.refresh_variant_inventory(
            variant=self.variant, business=self.business
        )

        inventory.refresh_from_db()
        # changed_type residue is never stock; historical rows are a record of
        # the past but still owned by the units ledger.
        self.assertEqual(inventory.quantity, 4)
        self.assertEqual(inventory.sellable, 2)
        self.assertEqual(inventory.reserved, 1)

    def test_refresh_on_normal_still_reads_received_supplies(self):
        self._make_normal_inventory(quantity=5, sellable=5)
        self._receive_supply(quantity=8)

        self.service.refresh_variant_inventory(
            variant=self.variant, business=self.business
        )

        inventory = Inventory.objects.get(variant=self.variant)
        self.assertEqual(inventory.quantity, 8)

    def test_summaries_do_not_double_count_serialized_stock(self):
        """The list annotation must agree with get_summary for serialized.

        Inventory.quantity already mirrors the units via
        _sync_inventory_summary, so adding the unit rows on top counted every
        serialized variant twice and treated changed_type residue as stock.
        """
        self._make_serialized_inventory(in_stock=2, changed_type=3)

        summary = self.service.get_summary(self.variant, business=self.business)
        annotated = self.service.annotate_variant_summaries(
            ProductVariants.objects.filter(pk=self.variant.pk)
        ).get()

        self.assertEqual(summary["total_item_count"], 2)
        self.assertEqual(annotated.total_item_count, summary["total_item_count"])
        self.assertEqual(
            annotated.sellable_item_count, summary["sellable_item_count"]
        )
        self.assertEqual(annotated.reserved_item_count, 0)
