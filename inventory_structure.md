# Inventory Domain Structure

Reference for `domains/inventory/` — warehouses, stock tracking, and inventory strategies.

## Layout

```text
domains/inventory/
├── admin.py                          django-unfold admin registrations
├── apps.py                           AppConfig (domains.inventory)
├── tests.py                          VariantInventoryAPITests
├── api/
│   ├── urls.py                       mounted at /api/inventory/
│   ├── views.py                      APIView classes + permissions
│   └── serializers.py                request/response/query serializers
├── enums/
│   ├── InventoryStrategyEnum.py      NORMAL = "normal", SERIALIZED = "serialized"
│   ├── WarehouseStatusEnum.py        AVAILABLE = 1, UNAVAILABLE = 2
│   ├── SerializedStockStatusEnum.py  IN_STOCK = 1, SOLD = 2, RETURNED = 3, DAMAGED = 4, LOST = 5
│   ├── InventorySupplyCostTypeEnum.py SHIPMENT, CUSTOMS, INSURANCE, TAX, COMMISSION, HANDLING, STORAGE, OTHER (lowercase persisted codes)
│   ├── VariantCostStrategyEnum.py    LATEST, WEIGHTED_AVERAGE, FIFO_NEXT (latest / weighted_average / fifo_next)
│   └── VariantPriceHistorySourceEnum.py INVENTORY_PRICING / MANUAL
├── models/                           11 models (see below)
└── services/
    ├── inventory_service.py          InventoryService (stock business rules)
    ├── inventory_cost_service.py     InventoryCostService (landed-cost calculations)
    ├── inventory_supply_service.py   InventorySupplyService (supply history, receiving, FIFO consumption/reversal)
    ├── inventory_pricing_service.py  InventoryPricingService (configuration, calculations, explicit apply/history)
    └── inventory_reporting_service.py InventoryReportingService (read-only financial metrics)
```

## Models

| Model | Table | Purpose |
|---|---|---|
| `InventoryStrategy` | `inventory_strategies` | Per-variant stock-handling configuration (`normal`, `serialized`). Configuration only, not logic. |
| `WarehouseStatus` | `inventory_warehouse_status` | Reference rows: `available`, `unavailable`. |
| `Warehouse` | `inventory_warehouse` | Physical warehouse with location and default flag. |
| `WarehouseStock` | `inventory_warehouse_stock` | Aggregate quantity row per `(variant, warehouse)` for the **normal** strategy. |
| `SerializedStockStatus` | `inventory_serialized_stock_status` | Reference rows keyed by code (`in_stock`, `sold`, ...). |
| `SerializedStock` | `inventory_serialized_stock` | One row per physical unit (serial number) for the **serialized** strategy. |
| `InventorySupply` | `inventory_supply` | A historical purchase/replenishment batch used as the foundation for inventory costing. It stores the original purchased quantity, remaining cost-layer quantity, purchase unit price, warehouse, and supply date. |
| `InventorySupplyCost` | `inventory_supply_cost` | An expense associated with a specific inventory supply batch that contributes to its real acquisition/landed cost. |
| `InventorySupplyConsumption` | `inventory_supply_consumption` | COGS snapshot linking one sold order item to the specific supply layer(s) it consumed, with the landed unit cost captured at sale time. |
| `VariantPricing` | `inventory_variant_pricing` | Per-variant pricing configuration (one-to-one): expected profit percentage and the cost-basis strategy for a future suggested selling price. Configuration only — no calculated price is stored. |
| `VariantPriceHistory` | `inventory_variant_price_history` | Immutable audit snapshot for an explicitly applied catalog-price change, including old/new prices and the cost/profit context used at application time. |

### Warehouse

- `code` (unique, max 20) auto-generated as `WH-{id:05d}` on first save.
- `city` FK → `location.City` (PROTECT), plus `address`, `lat`/`lng` (DecimalField), `phone_numbers` JSON list, `postal_code`.
- `is_default` boolean guarded by a partial unique constraint (`inventory_single_default_warehouse`) so exactly one default can exist.
- `status` FK → `WarehouseStatus` (PROTECT).

### WarehouseStock (normal strategy)

- FK `variant` → `catalog.ProductVariants` (PROTECT), FK `warehouse` → `Warehouse` (PROTECT); unique together.
- Counters: `quantity`, `sellable`, `reserved` (default 0), `min_stock` (default 0).
- Property `available = sellable - reserved`.
- DB invariants (CheckConstraints):
  - `sellable <= quantity` (`inventory_stock_sellable_lte_quantity`)
  - `reserved <= sellable` (`inventory_stock_reserved_lte_sellable`)
- Custom permissions: `view_inventory`, `adjust_stock`.

### SerializedStock (serialized strategy)

- FKs `variant` → `catalog.ProductVariants`, `warehouse` → `Warehouse`, `status` → `SerializedStockStatus` (all PROTECT).
- Flags `sellable` (bool, default True) and `reserved` (bool, default False).
- `serial_number`: case-insensitively globally unique via `UniqueConstraint(Lower("serial_number"))`; whitespace-normalized in `save()`.
- "Available" means `status.code == "in_stock" AND sellable AND not reserved`.

### Strategy linkage

The strategy lives on the catalog side: `ProductVariants.inventory_strategy` FK (see `domains/catalog/models/product_variants.py:26`). The inventory domain reads it to decide which storage model applies.

### InventorySupply (costing foundation)

A historical purchase/replenishment batch used as the foundation for inventory costing. It stores the original purchased quantity, remaining cost-layer quantity, purchase unit price, warehouse, and supply date. No service, API, or stock integration exists yet; later steps will add FIFO consumption on top of this persistence layer.

- FKs `variant` → `catalog.ProductVariants` and `warehouse` → `Warehouse`, both PROTECT with `related_name="inventory_supplies"`.
- `quantity` is the original purchased amount (`> 0`); `remaining_quantity` starts equal to `quantity` on creation and will later be decremented by FIFO consumption.
- `unit_buy_price`: money convention `DecimalField(max_digits=15, decimal_places=2)`, non-negative.
- `supplied_at` drives default ordering `["supplied_at", "id"]` so future FIFO processing consumes the oldest layer first; plus optional `reference_number`, `invoice_number`, `notes`, and `created_at`/`updated_at`.
- DB invariants (named CheckConstraints): `quantity > 0`, `remaining_quantity >= 0`, `remaining_quantity <= quantity`, `unit_buy_price >= 0`. Composite index on `(variant, warehouse, supplied_at)`.

**Important:** `remaining_quantity` is a costing concept and is independent from inventory availability, sellable stock, and reservations. It must not be connected to `WarehouseStock.sellable`, `WarehouseStock.reserved`, `WarehouseStock.available`, or `SerializedStock.reserved`. A variant may have `WarehouseStock.available = 30` while its supply layers read 5 + 10 + 15; these are separate concepts that stay architecturally independent.

### InventorySupplyCost (supply expenses)

An expense associated with a specific inventory supply batch that contributes to its real acquisition/landed cost. Rows cascade with their supply (`related_name="costs"`); multiple rows of the same type are allowed (e.g. two freight charges), so there is no `(supply, type)` uniqueness.

- Cost types are system-defined accounting categories persisted as lowercase codes through `InventorySupplyCostTypeEnum`: `shipment`, `customs`, `insurance`, `tax`, `commission`, `handling`, `storage`, `other`. They are model choices, not database reference rows.
- `amount`: money convention `DecimalField(max_digits=15, decimal_places=2)`, non-negative (`inventory_supply_cost_amount_gte_zero` check constraint). Negative credit/refund entries would be modeled explicitly later.
- Optional `description`; plus `created_at`/`updated_at`.
- Cost rows never touch stock, reservations, or the supply's `remaining_quantity`.

### Landed-cost calculation (`InventoryCostService`)

Authoritative formulas live only in `domains/inventory/services/inventory_cost_service.py`:

```text
base_cost_total  = quantity × unit_buy_price
extra_cost_total = sum(InventorySupplyCost.amount)   # 0 when no cost rows
landed_cost_total = base_cost_total + extra_cost_total
landed_unit_cost = landed_cost_total / original quantity
```

Example: quantity 10 × unit price 100,000 = 1,000,000 base; +100,000 extra costs → 1,100,000 landed total → 110,000 landed unit cost.

- **Cost calculations use the original `InventorySupply.quantity`, not `remaining_quantity`.** `remaining_quantity` tracks future FIFO cost consumption and has no effect on the historical landed unit cost of a supply.
- All math uses `Decimal` (never float); operands are coerced with `Decimal(...)` so freshly created instances holding raw string values still compute correctly. Intermediate totals stay exact — no premature quantization; division uses Python's decimal context.
- API: `get_base_cost_total(supply)`, `get_extra_cost_total(supply)`, `get_landed_cost_total(supply)`, `get_landed_unit_cost(supply)`, plus `get_cost_summary(supply)` returning all four values as one dict for serialization/admin display.
- No FIFO, pricing-policy, or order responsibilities yet; no denormalized calculated columns are stored.

## Service: `InventoryService`

Single service class owning all rules; raises `InventoryService.ValidationError(errors)` mapped to DRF validation errors by views.

Variant summaries:

- `annotate_variant_summaries(queryset)` — subquery annotations per strategy (`normal_*`, `serialized_*`) collapsed into `total_item_count`, `sellable_item_count`, `available_item_count` via `Case` on strategy code.
- `search_variants(...)` — admin inventory list query: search (SKU/product name), product/category filters, `strategy_code`, `stock_state` (`in_stock` / `out_of_stock` / `low_stock` vs `min_stock` from the default warehouse), `has_reserved`, ordering allowlist.
- `serialize_variant_overview(variant, default_warehouse)` / `get_summary(variant)` / `get_variant_details(variant)` — read shapes for list and detail responses.

Warehouses:

- `search_warehouses(...)`, `get_warehouse(id, lock=...)`, `get_default_warehouse(lock=...)` — the latter enforces exactly one default warehouse.
- `create_warehouse` / `update_warehouse` / `delete_warehouse` — atomic with table locks:
  - First warehouse created becomes default automatically.
  - Default flag moves atomically; the current default cannot be changed while it holds stock; cannot unset default if it is the only one; default cannot be deleted; PROTECT errors become "contains stock" validation errors.

Stock mutation (the core workflow):

- `apply_variant_inventory(variant, *, strategy_code, inventory=None, serial_items=None, inventory_submitted=False)`
  - Validates strategy ∈ {normal, serialized}; switching strategies requires the old strategy to be empty (zero-quantity normal rows are deleted, serialized rows must not exist).
  - Normal: upserts the default-warehouse `WarehouseStock` snapshot preserving existing `reserved`; enforces `0 <= reserved <= sellable <= quantity`.
  - Serialized: full-snapshot replacement — omitted editable rows are deleted; sold/reserved/historical rows are neither deletable nor editable; serial uniqueness checked casefolded in Python and by DB constraint; swapped serial values staged through temporary `__inventory_tmp_*` values to avoid unique collisions mid-transaction.
- `adjust_variant_stock(variant, ...)` — locks the variant row then delegates to `apply_variant_inventory`.
- `validate_variant_deletion(variant)` — variants with any stock cannot be deleted.

Helpers: `normalize_serial(value)`, `_is_editable(row)` (`in_stock` and not reserved), `serialize_warehouse(warehouse)`, `get_strategies()`.

## API (`/api/inventory/`, no trailing slashes)

Authentication: `AdminJWTAuthentication`. Standard `api_response` envelope; lists paginated (20/page).

| Route | View | Method(s) | Permission |
|---|---|---|---|
| `/api/inventory/variants` | `InventoryVariantList` | GET | `inventory.view_inventory` |
| `/api/inventory/variants/<variant_id>` | `VariantInventoryDetail` | GET | `inventory.view_inventory` |
| same | | PATCH | `view_inventory` + `inventory.adjust_stock`; body must contain exactly one of `inventory` (normal) or `serial_items` (serialized) matching the variant's strategy |
| `/api/inventory/warehouses` | `WarehouseListCreate` | GET / POST | DjangoModelPermissions on `Warehouse` |
| `/api/inventory/warehouses/<warehouse_id>` | `WarehouseDetail` | GET / PATCH / DELETE | DjangoModelPermissions on `Warehouse` |
| `/api/inventory/warehouse-statuses` | `WarehouseStatusOptions` | GET | view_inventory |
| `/api/inventory/strategies` | `InventoryStrategyOptions` | GET | view_inventory |
| `/api/inventory/serialized-statuses` | `SerializedStatusOptions` | GET | view_inventory |
| `/api/inventory/supplies` | `SupplyListCreate` | GET / POST | GET: `inventory.view_inventory`; POST: + `inventory.adjust_stock` |
| `/api/inventory/supplies/<supply_id>` | `SupplyDetail` | GET / PATCH / DELETE | GET: view_inventory; PATCH/DELETE: + adjust_stock |
| `/api/inventory/supplies/<supply_id>/receive` | `SupplyReceive` | POST | view_inventory + adjust_stock; body: `{serial_items: [{serial_number}...]}` for serialized variants, empty for normal |
| `/api/inventory/supply-cost-types` | `SupplyCostTypeOptions` | GET | view_inventory |
| `/api/inventory/variants/<variant_id>/pricing` | `VariantPricingView` | GET / PATCH | GET: view_inventory; PATCH: + adjust_stock. Closed write serializer accepts either/both fields; GET/PATCH return the full pricing overview (all three cost methods, selected basis, suggested price) |
| `/api/inventory/variants/<variant_id>/pricing/apply` | `VariantPricingApplyView` | POST | view_inventory + adjust_stock + `catalog.change_productvariants`; optional `{price}` override, otherwise applies current suggested price |
| `/api/inventory/variants/<variant_id>/pricing/history` | `VariantPricingHistoryView` | GET | view_inventory; newest-first immutable snapshots |
| `/api/inventory/pricing` | `PricingListView` | GET | view_inventory. Paginated variant list with per-row pricing; filters `search`, `category_id`, `strategy`, `has_pricing`, ordering allowlist (`sku`, `product_name`, `current_price`, `remaining_quantity`) |
| `/api/inventory/pricing-strategies` | `PricingStrategyOptions` | GET | view_inventory |

### Variant pricing configuration

`VariantPricing` is a one-to-one configuration per variant: `expected_profit_percentage` (`DecimalField(5,2)`, DB-checked `>= 0`, default 0) and `cost_strategy` — a system-defined choice from `VariantCostStrategyEnum`: `latest`, `weighted_average`, `fifo_next`. No suggested selling price or cost basis is stored here; both are calculated on demand and never persisted, and catalog prices are never updated automatically.

Strategy meanings (implemented in `InventoryPricingService` over received supplies with `remaining_quantity > 0`):

```text
latest        → landed_unit_cost of the newest supply   (supplied_at DESC, id DESC)
fifo_next     → landed_unit_cost of the oldest supply    (supplied_at ASC, id ASC)
weighted_average → SUM(remaining_quantity * landed_unit_cost) / SUM(remaining_quantity)

suggested_price = cost_basis * (1 + expected_profit_percentage / 100)
```

- Landed unit cost per layer mirrors `InventoryCostService`: `(quantity × unit_buy_price + extra costs) / quantity`; a single JOIN aggregate avoids per-supply queries.
- All math uses exact `Decimal`; results are quantized to currency precision only at the API boundary. Unreceived supplies and zero-remaining supplies are ignored. When no received supply with remaining quantity exists, `cost_basis` and `suggested_price` are `null` (never zero).
- `GET/PATCH /api/inventory/variants/<id>/pricing` merge the config with the full overview (`latest_cost`, `weighted_average_cost`, `fifo_next_cost` for side-by-side comparison, plus selected `cost_basis`, `suggested_price`, `total_remaining_supply_quantity`, read-only `catalog_price`). An unconfigured variant still returns the overview with null config fields.
- `GET /api/inventory/pricing` lists every variant with its pricing row via `InventoryPricingService.search_pricing` + `get_pricing_overview_map`: constant query count per page (variants+configs+remaining annotation in one query, then one batched supplies-and-costs query for just the page's variants), so there is no N+1 over supplies, costs, configs, or products.
- Catalog prices remain unchanged when supplies, costs, strategies, or expected-profit percentages change. `POST .../pricing/apply` is the only inventory-pricing workflow that writes `ProductVariants.price`: it row-locks the variant, requires a current non-null cost basis and suggested price, applies either the suggestion or the optional custom override, and creates `VariantPriceHistory` in the same transaction. Suggested applications use source `inventory_pricing`; custom overrides use `manual`. Any history-write failure rolls the catalog price back.
- History snapshots store `old_price`, `new_price`, `cost_basis`, selected strategy, expected profit, source, and creation time. The variant FK uses PROTECT so applied-price audit history cannot disappear through variant deletion.

Managed by `InventoryPricingService.get_variant_pricing` / `update_variant_pricing` (defensive upsert under row lock with service-level strategy/profit validation), `get_cost_basis`, `get_suggested_price`, `get_pricing_summary`, `get_variant_pricing_overview`, `search_pricing` / `get_pricing_overview_map`, `apply_price`, `get_price_history`, and `get_strategies`.

### Supply APIs (`InventorySupplyService`)

**Scope:** Supply APIs currently manage purchase/cost history only. They do not yet receive physical stock into `WarehouseStock` or `SerializedStock`; creating, updating, or deleting supplies never touches inventory quantities, reservations, or serialized rows.

List query parameters: `search` (variant SKU, product name, reference number, invoice number), `variant_id`, `warehouse_id`, `date_from`/`date_to` (`supplied_at` bounds), `has_remaining` (`true` → `remaining_quantity > 0`, `false` → `= 0`), and `ordering` restricted to an allowlist (`supplied_at`, `created_at`, `quantity`, `remaining_quantity`, `unit_buy_price`, each with `-` prefix). Unknown ordering values fall back safely to the default. List default order is newest-first (`-supplied_at, -id`) for admin history UIs; the model's FIFO-friendly `supplied_at, id` ordering is unchanged. Rows carry server-calculated `base_cost_total`, `extra_cost_total`, `landed_cost_total`, and `landed_unit_cost` (`extra_cost_total` uses a single `Coalesce(Sum(costs__amount))` annotation; totals mirror `InventoryCostService`). Detail additionally returns `notes` and nested `costs` rows with totals from `InventoryCostService`.

Write rules:

- All write serializers are closed — unknown fields (e.g. `some_random_field`, `remaining_quantity`, or calculated fields like `landed_cost_total`) are rejected.
- POST accepts `variant_id`, `warehouse_id`, `quantity` (> 0), `unit_buy_price` (>= 0), `supplied_at`, optional `reference_number`/`invoice_number`/`notes`, and optional nested `costs` (`type` from `InventorySupplyCostTypeEnum`, `amount` >= 0, optional `description`). Creation is atomic; an invalid cost row rolls back the whole supply. **`remaining_quantity` is server-controlled**: it is initialized to `quantity` internally and can never be submitted.
- PATCH allows `warehouse_id`, `unit_buy_price`, `supplied_at`, reference/invoice/notes, `costs`, and `quantity`. Quantity changes are allowed only while `remaining_quantity == quantity` (never consumed); a safe change resets `remaining_quantity` to the new quantity automatically. Submitted `costs` replace the full cost snapshot transactionally (rows have no historical consumers yet); submitted `id` values in cost rows are rejected by the closed serializer.
- DELETE is allowed only when `remaining_quantity == quantity`; consumed supplies cannot be deleted ("Supply has already been consumed and cannot be deleted."). Received supplies can never be deleted. CASCADE removes the supply's cost rows.

### Receiving supplies into physical inventory

`POST /api/inventory/supplies/<id>/receive` (via `InventorySupplyService.receive_supply`, which delegates stock mutations to `InventoryService.receive_normal_stock` / `receive_serialized_stock`). Receiving is a one-time, additive delta operation executed atomically with row locks (`select_for_update` on the supply plus target stock rows); it either fully succeeds or fully rolls back.

- Sets `received_at` once; `is_received = received_at is not None` is exposed in list/detail responses. A second receive attempt is rejected without side effects.
- **Normal strategy**: `WarehouseStock.quantity += supply.quantity` and `sellable += supply.quantity`, creating the `(variant, warehouse)` row if missing. `reserved`, `min_stock`, and the supply's `remaining_quantity` are never touched.
- **Serialized strategy**: requires exactly `supply.quantity` serial items; creates `SerializedStock` rows (`status=in_stock`, `sellable=True`, `reserved=False`) reusing existing serial normalization/case-insensitive uniqueness rules. Each created row references its batch through the nullable `SerializedStock.supply` FK (PROTECT). Any failure — including a duplicate serial discovered mid-batch — rolls back all created rows.
- **Received-supply restrictions**: variant, warehouse, and quantity become immutable; deletion is blocked. Cost fields (`unit_buy_price`, `costs` snapshot), `reference_number`, `invoice_number`, and `notes` remain editable.
- List/detail expose `received_at`/`is_received`; list supports `?received=true|false`.
- Receiving does not consume cost layers: `remaining_quantity` is reserved for future FIFO consumption.

### Supply consumption (FIFO cost layers on finalized sales)

`InventorySupplyConsumption` records which supply layer(s) each sold order item consumed: `supply` + `order_item` (PROTECT FKs, unique together), `quantity > 0`, and a money snapshot — `unit_cost` (landed unit cost quantized to currency precision at sale time) and `total_cost = quantity * unit_cost`, enforced by a DB check constraint. Historical COGS never shifts when supplies are edited later. `reversed_quantity` (default 0, DB-checked `0 <= reversed_quantity <= quantity`) tracks how much of the record has been restored by cancellation/returns.

`InventorySupplyService.consume_order_item(order_item)` runs inside the caller's transaction:

- Guarded per item (row-locked, raises if the item already has consumptions).
- **Normal strategy**: resolves sold warehouses from the item's reservations, then consumes FIFO — received supplies for `(variant, warehouse)` with `remaining_quantity > 0`, ordered `supplied_at ASC, id ASC`, locked with `select_for_update`. One consumption row per touched layer; `remaining_quantity` decreases accordingly. If total remaining is less than the sold quantity, the whole operation fails atomically (`remaining_quantity < 0` is unreachable). Stock that never entered through the supply system (legacy/dev fixtures) sells without COGS attribution.
- **Serialized strategy**: no blind FIFO — each sold `SerializedStock` row's `supply` FK identifies its exact layer; counts are grouped per supply and decremented there. Units without supply linkage (pre-existing rows) are skipped.
- Duplicate prevention is also enforced at DB level via the `(order_item, supply)` unique constraint.

**Order integration point**: `OrderService.consume_reservations(order)` — called only from payment approval (`payments/services.py::review_payment`, inside its atomic block). Cart validation, checkout reservation, pending/processing payments, and expiry release never touch consumption; expired/cancelled orders release stock instead.

### Consumption reversal (cancellations and returns)

`InventorySupplyService.reverse_order_item_consumption(order_item, *, quantity=None)` restores consumed quantities to the **exact original supplies** — consumption records are the source of truth and FIFO is never recalculated:

- Locks the order item plus its consumption rows (and the joined supply rows) with `select_for_update`.
- `quantity=None` reverses every unreversed unit (full cancellation); a number reverses exactly that many units, taking from the **most recently consumed layer first** (`created_at DESC, id DESC`) so partial returns unwind LIFO.
- Each restored unit increments `supply.remaining_quantity` and `consumption.reversed_quantity`; the DB constraints cap reversal at the original quantity, so a layer can never be restored more than it yielded. Over-requesting raises; repeated full reversals are no-ops returning 0.
- Cost-layer restoration only — physical stock restoration stays with the existing order logic.

**Integration points**: `OrderService.execute_action("cancel")` reverses all items after releasing reservations (items without consumptions are no-ops), and `ReturnRequestService.execute_admin_action(..., "complete")` reverses exactly the returned quantities per return item once goods are accepted. Items sold before supply tracking existed are skipped.

Cost-type options come directly from `InventorySupplyCostTypeEnum` as `{code, name}` option pairs.

Serializer notes:

- Write serializers subclass `ClosedSerializer` (rejects unknown fields).
- `WarehouseWriteSerializer`: validates lat/lng ranges, deduped non-blank phone numbers.
- `VariantStockWriteSerializer.validate` enforces exactly one snapshot key per submission.

## Admin

All eight models registered through `django-unfold` `ModelAdmin`. `WarehouseStockAdmin` exposes the `available` property; `SerializedStockAdmin` filters on status/warehouse/sellable/reserved and searches by serial number or SKU. `InventorySupplyAdmin` lists variant/warehouse/quantity/remaining quantity/unit price/supplied date plus reference and invoice numbers, shows calculated base/extra/landed-total/landed-unit-cost columns from `InventoryCostService`, edits costs through a tabular inline, and filters/searches by warehouse, supplied date, SKU, and reference/invoice number. `InventorySupplyCostAdmin` lists supply SKU/type/amount/description with type and supply-warehouse filters and searches across SKU, reference/invoice numbers, and description.

## Seeding

`core/management/seeders/inventory.py` (run via `python manage.py seed`):

1. Strategies `normal` and `serialized` with Persian-market descriptions (T-shirts vs mobile phones).
2. `WarehouseStatus` rows seeded by enum id (`available`=1, `unavailable`=2).
3. `SerializedStockStatus` rows seeded by enum-derived codes (`in_stock`, `sold`, `returned`, `damaged`, `lost`).
4. Default warehouse `WH-00001` ("Warehouse Tehran", Tehran coordinates) requires location seeding first.

Migration `0004_ensure_normal_inventory_strategy.py` guarantees the `normal` strategy exists; `0006_inventory_permissions.py` installs the custom permissions.

## Cross-Domain Usage

- **catalog**: owns `ProductVariants.inventory_strategy`; catalog services call `InventoryService.apply_variant_inventory` during aggregate writes and `validate_variant_deletion` before removing variants. Catalog serializers/search annotate availability through `annotate_variant_summaries`.
- **cart**: uses `InventoryService` (and its annotated `available_item_count`) to validate line quantities, cap quantities to stock, and flag pre-order fallbacks.
- **order**: checkout reserves stock with row locks — decrementing `WarehouseStock.sellable`/`quantity` for normal items and flipping `SerializedStock.status` to `sold` for serialized items; cancellation/release updates the same rows using reservation records typed `warehouse_stock` / `serialized_stock`. On payment approval, `consume_reservations` additionally calls `InventorySupplyService.consume_order_item` per item to consume FIFO cost layers (see below).

## Conventions And Invariants To Preserve

- Exactly one default warehouse at all times; enforced by constraint + service checks under row locks.
- Stock mutations go through `InventoryService` with `transaction.atomic` + `select_for_update`; never write `WarehouseStock`/`SerializedStock` ad hoc from other domains' request paths (order services are the sanctioned exception pattern with explicit locking).
- Serial numbers: trimmed, casefold-unique across the whole table.
- Strategy transitions only when the current strategy holds no stock.
- Tests: `python manage.py test domains.inventory.tests`.
