# UzShop Backend

## Purpose

Django REST API for UzShop's admin and customer applications. Business code is organized by domain, with services handling workflows and shared infrastructure under `core/`.

This directory is a Git submodule and a separate repository. Commit backend changes here before updating the parent repository's submodule pointer. Preserve unrelated changes in a dirty worktree.

## Stack

- Python 3.12
- Django 5.2 and Django REST Framework
- SimpleJWT with separate customer and admin principals
- PostgreSQL
- Redis for Celery and confirmed requests
- Celery workers for notification delivery
- django-storages and boto3 for optional S3-compatible file storage
- Gunicorn and django-unfold

## Commands

Run directly from `back/`:

| Command | Purpose |
|---|---|
| `pip install -r requirements.txt` | Install dependencies |
| `python manage.py runserver` | Start Django locally |
| `python manage.py check` | Run system checks |
| `python manage.py migrate` | Apply migrations |
| `python manage.py makemigrations` | Generate migrations |
| `python manage.py seed` | Seed development/reference data |
| `python manage.py seed_categories` | Idempotently load the canonical category taxonomy |
| `python manage.py purge_changed_type_units --older-than-days 90` | Purge expired `changed_type` units left by an inventory type conversion |
| `pip install -r scripts/requirements-digikala-discovery.txt` | Install Playwright+Chromium deps for Digikala mapping discovery |
| `python scripts/discover_all_categories.py` | Discover/merge Digikala mappings one by one |
| `python scripts/digikala.py validate\|listings\|details ...` | Run the Digikala import CLI |
| `python manage.py test` | Run all tests |
| `python manage.py test domains.customer.tests` | Run a focused suite |
| `python manage.py makemessages -l fa -l en` | Update translations |
| `python manage.py compilemessages` | Compile translations |

From the workspace root, prefer the running stack when dependencies are needed:

```bash
docker compose exec -T django python manage.py check
docker compose exec -T django python manage.py migrate
docker compose exec -T django python manage.py test
```

Gunicorn does not reload bind-mounted code. Restart the `django` service before testing backend changes through Nginx or a frontend.

## Structure

```text
config/                 Settings, root URLs, Celery, ASGI, WSGI
core/                   Shared responses, exceptions, services, utilities
domains/catalog/        Categories, products, variants, and media relations
domains/content/        Landing pages, component configuration, reusable SEO records
domains/customer/       Customer auth, profiles, preferences, and addresses
domains/files/          Provider-neutral stored-file lifecycle
domains/importing/      External-source import pipelines (Digikala, etc.)
domains/inventory/      Warehouses, stock, and inventory strategies
domains/location/       Countries, states, and cities
domains/marketplace/    BusinessOffer pricing, plus the marketplace basket, order, payment, and return flows
domains/notifications/  Provider records, audit rows, and delivery workers
domains/users/          Administrative users, auth, and permissions
locale/                 Django translations
```

Keep domain behavior in its owning domain. Shared infrastructure belongs in `core/`; shared business behavior usually does not.

## Design Boundaries

Use this direction for new work:

```text
Request -> View -> Serializer -> Domain Service -> Model / Infrastructure
```

Views:

- Authenticate and authorize.
- Validate HTTP input through serializers.
- Call domain services.
- Paginate and return the standard response envelope.

Serializers:

- Validate request shape and represent responses.
- Avoid multi-model workflows and cross-domain mutations.

Services:

- Own reusable rules, queries, normalization, and multi-step workflows.
- Use `transaction.atomic()` when changes must commit together.
- Accept domain values and objects, not DRF `Request` or `Response` instances.
- Call another domain's public service instead of mutating its models directly.

Models and the database:

- Enforce invariants that must hold for every caller.
- Keep HTTP concerns out of models.

Do not add abstraction around trivial ORM operations unless it protects a rule or creates a meaningful domain boundary. Some older code does not fully follow these layers; improve it locally rather than copying the exception.

## API Conventions

Root namespaces:

- `/api/users/`
- `/api/customer/`
- `/api/catalog/`
- `/api/importing/`
- `/api/inventory/`
- `/api/location/`
- `/api/files/`
- `/api/order/`
- `/api/marketplace/`
- `/api/notifications/`

Return `core.responses.api_response` envelopes:

```json
{
  "success": true,
  "message": "",
  "data": null,
  "errors": null
}
```

Paginated results belong inside `data` as `count`, `next`, `previous`, and `results`. Page-number pagination defaults to 20 items.

- Authentication is required by default; mark public views explicitly.
- Most routes omit trailing slashes. Preserve the existing route contract.
- Create operations generally return 201, confirmation initiation returns 202, and deletes commonly return a 200 envelope.
- Keep filtering, ordering allowlists, annotations, and related-object loading on the server.
- Normalize exceptions through the configured exception handler; do not return ad-hoc error shapes.

## Authentication And Confirmation

Admin and customer JWTs both require a `user_type` claim. Admin tokens represent active staff users; customer tokens recheck customer status and password-hash revocation.

Customer login is intentionally two-step:

1. Validate phone/password and create an SMS challenge without issuing tokens.
2. Consume the one-time code, recheck account state, issue tokens, and update `last_login`.

Confirmed requests use `core.services.confirmed_request.ConfirmedRequestService` and dedicated Redis storage.

- Codes are HMAC-hashed and bound to request ID, purpose, and subject.
- Challenges enforce expiry, cooldown, attempt limits, and one-time consumption.
- A newer challenge invalidates the previous challenge for the same purpose and subject.
- Do not reimplement Redis keys, code comparison, or challenge lifecycle in a domain.
- A static development code is valid only when `CONFIRMED_REQUEST_DEV_MODE=True`.

Phone writes and lookups must use `core.utils.phone.normalize_phone`. Forgot-password initiation is account-enumeration safe and must retain the same public response shape for eligible and ineligible phones. Password reset returns no JWT and must invalidate old credentials through the password fingerprint.

No JWT refresh, logout, or refresh-token revocation endpoint is currently mounted.

## Notifications

Notifications are provider-neutral audit records delivered asynchronously through Celery.

- Call `SMSService`; do not enqueue provider tasks directly from views.
- Sending requires an active provider and normally an active default SMS provider.
- The only implemented adapter is `fake-sms`, guarded by `NOTIFICATIONS_ALLOW_FAKE_SMS`.
- Sensitive bodies remain available only while pending and are redacted after success, failure, queue failure, or expiry cleanup.
- Never expose confirmation codes or sensitive notification bodies through APIs, admin, or logs.
- A successful 202 response means queued, not delivered.

The seed command does not provision notification provider statuses or a default provider. Fresh development databases need those records before SMS-backed customer flows can work. Production needs a real SMS adapter and external credential configuration.

## Files, Catalog, And Inventory

- The Files domain owns object lifecycle; Catalog owns product-file relationships.
- Store provider-neutral object keys, not bucket names, credentials, or permanent URLs.
- Generate URLs through `FileService` and the configured storage alias.
- Only available files may be attached to products.
- Use Catalog services for aggregate product, category-detail, variant, and media writes.
- Use Inventory services for stock mutations and strategy-specific rules.
- Preserve database constraints, row locking, and atomic replacement workflows when changing aggregate writes.
- Inventory type changes require an inactive marketplace offer; `InventoryService.inventory_type_change_gate(variant, business)` reports the rule without raising.
- Converting serialized → normal moves live units to the `changed_type` state. They keep the audit trail but are never sellable and are excluded from stock totals. Purge them manually with `python manage.py purge_changed_type_units --older-than-days 90` (`--dry-run` previews); there is deliberately no beat schedule, so the 90-day retention window stays an operator decision.

Current catalog endpoints are administrative and permission-controlled. They are not a public storefront contract.

## Marketplace Domain

The marketplace domain owns per-business variant pricing through `BusinessOffer`.

- `BusinessProfile` is scoped per `Vendor` through the `business_profile_one_per_vendor` constraint; `vendor` is nullable, and `inventory.0022` seeds `id=1` so migrated inventory rows have a business to point at. `business.0004` removed the old global singleton, so the schema alone does not enforce "only one business exists".
- `BusinessOffer` has a unique constraint on `(business, variant)`. Each variant can have at most one offer per business.
- `BusinessOffer` owns `price`, `discount_type`, and `discount_value`. These fields were removed from `ProductVariants`.
- `OfferPriceHistory` is an append-only audit of price/discount changes, written by `MarketplacePricingService` for both the admin offer API and the vendor variant API. An omitted field keeps its stored value; an explicit `None` clears it. It is separate from `inventory.VariantPriceHistory`, which still records the cost-basis pricing flow.
- `BusinessOffer.is_active` is also the gate for changing a vendor variant's inventory type.
- `BusinessOffer.is_active` is purely the marketplace **listing** flag. Storefront, cart, order, catalog price filters, and inventory reporting keep `is_active=True`; pricing configuration, vendor pricing views, and the admin pricing list read the offer regardless of it.
- Pricing configuration (`expected_profit_percentage`, `cost_strategy`) lives on `BusinessOffer` and does not require one to exist first: `InventoryPricingService.update_variant_pricing()` creates a draft offer with `is_active=False` when the variant has none. Nothing in the pricing flow activates an offer — a variant becomes visible only through an explicit marketplace-status change.
- `cost_strategy` is a `PROTECT` foreign key to `PricingStrategy` (`marketplace_pricing_strategy`, default id 1 = `latest`), seeded by `marketplace.0007` from `domains/marketplace/data/pricing_strategies.py`. The row holds `code`, `name`, `fa_name`, and a `description` content-component document (`{components: [{id, key, version, props}]}`) that the panels render as the per-strategy user guide through their existing content registry.
- `PricingStrategy` is reference data: seed-only, with no admin or vendor write path, so adding a strategy requires a `VariantCostStrategyEnum` member, a seed row, a `InventoryPricingService._calculate_basis()` branch, and a new migration. The enum remains the validation vocabulary for request codes; the table only supplies display data. `domains.marketplace.tests_pricing_strategy` asserts the two never drift apart.
- Code strings are the API contract in both directions. Only the persistence layer resolves them to rows (`MarketplacePricingService.resolve_strategies` used by `create_offer` / `update_offer`, and `InventoryPricingService._strategy_row`); readers emit `offer.cost_strategy.code`. `OfferPriceHistory.cost_strategy` keeps its own `CharField` code snapshot so the audit trail does not move with the reference data.
- Reading pricing: callers attach `_business_offer` to variant objects via a batched lookup, then read from `offer.price`, `offer.discount_type`, `offer.discount_value`.
- Writing pricing: `InventoryPricingService.apply_price()` writes to `BusinessOffer.price` and creates `VariantPriceHistory` snapshots. `GET .../variants/<id>/pricing` accepts optional `cost_strategy` / `expected_profit_percentage` query params to calculate a suggested price from unsaved values without writing anything.
- `VariantService.calculate_discounted_price(variant, offer=None)` accepts an optional offer parameter and reads price/discount from it.
- Cart, order, storefront, and search backends must attach `_business_offer` to variant objects before reading pricing.
- The Digikala import pipeline no longer writes pricing to variants. Pricing is applied separately via inventory pricing.
- Product search price filters (`price_operator`, `price`, `price_min`, `price_max`) filter on `BusinessOffer.price` with `is_active=True`.
- The storefront search API (`/api/catalog/storefront/products`) serves pricing from `BusinessOffer` through `StorefrontProductService`.

### Marketplace Orders

The marketplace runs a basket, checkout, payment, and return flow parallel to the shop's, over its own tables, by extending the shop's service layer rather than copying it.

- Tables: `MarketplaceCart`/`MarketplaceCartItem`, `MarketplaceOrder`/`MarketplaceOrderItem`, `MarketplaceOrderPayment` + `MarketplacePaymentDocument`, and `MarketplaceReturnRequest` + its item/evidence rows. The order carries `business`; an item carries `variant` and `marketplace_offer`, so a priced line still identifies what was sold after the offer moves on.
- The shared machinery lives outside this domain and is extended, never duplicated: `BaseCartService` (`domains/cart/services.py`), `BaseCheckoutService` (`domains/cart/checkout.py`), `BaseOrderService` (`domains/order/flow.py`), `BaseReturnRequestService` (`domains/order/return_flow.py`). The marketplace services under `domains/marketplace/services/` subclass these and name their own tables; `domains.order` hosting the shared base is a deliberate one-way dependency.
- The offer price is snapshotted onto the item at checkout. Historical totals are never recomputed from the current offer.
- Reserve, release, consume, restore, and cancel stock have a single implementation. `InventorySupplyConsumption` references a shop `order_item` or a marketplace one; the schema requires exactly one, and `InventorySupplyConsumption._target_field()` derives which from the line's own class rather than asking the caller.
- `MarketplaceOrderSeeder` copies `ORDER_STATUSES` / `ORDER_ACTIONS` / `ORDER_STATUS_ACTIONS` from `core/management/seeders/order.py` into `marketplace_order_status` and friends, so both flows speak one vocabulary while keeping tables they may later diverge on.
- Customer routes under `/api/marketplace/`: `orders`, `orders/<id>`, `orders/<id>/pay`, `orders/<id>/actions`, `orders/<id>/actions/<code>`, `orders/<id>/cancel`, `payment-methods`, `returns`, `returns/<id>`.
- Admin routes under `/api/marketplace/admin/`: `orders`, `orders/<id>`, `orders/<id>/actions`, `orders/<id>/actions/<code>`, `orders/<id>/returns/<id>/actions/<code>`, `statuses`. They gate on `marketplace.view_marketplaceorder` / `marketplace.change_marketplaceorder`, and on `marketplace.view_marketcplacereturnrequest` to see returns — the shop's `order.*` permissions do not reach this list.
- Both route sets are the shop's views (`domains/order/views.py`, `domains/order/admin_views.py`) with a service attribute swapped, so the two flows answer with identical envelopes, status codes, and error shapes. Read the shop view before adding a marketplace endpoint.
- Order geography is deliberately absent for this flow; `/api/order/admin/orders/geography` remains shop-only.

### Order Geography

- `/api/order/admin/orders/geography` aggregates open orders from checkout-time address snapshots under `order.view_order`.
- Province and city counts include all open orders; foreign or incomplete locations are reported as unmapped rather than plotted on the Iran map.
- City marker coordinates belong to `location.City` and are populated from the attributed canonical coordinate data during migration and location seeding.
- Administrative order lists accept `state_id` and `city_id` snapshot filters alongside `in_progress=true`.

### Digikala Import (Importing Domain)

The Digikala integration lives in the `domains.importing` domain under
`domains/importing/integrations/digikala/`. The importing domain owns the
file-backed, migration-free pipeline: CLI, Celery tasks, and admin API.
Catalog writes go through `DigikalaImportService`, which delegates to
catalog services. Generated listing/job data lives outside the repository
under `DIGIKALA_RUNTIME_ROOT` (gitignored `runtime/`).

Pricing is no longer written during import. The import pipeline skips `price`,
`discount_type`, and `discount_value` when creating or updating variants.
Pricing is applied separately through the inventory pricing service once
a `BusinessOffer` exists for the imported variant.

Pipeline:

1. **Mapping discovery** — `scripts/discover_all_categories.py` reads
   `core/management/data/categories.json`, discovers the Digikala API endpoint for each
   leaf category, and merges results **one by one** into
   `core/management/data/digikala_category_mappings.json`. It resumes from the existing
   file and dedupes by `category_id`, so progress survives interruption. Requires
   Playwright + Chromium and internet access to digikala.com
   (`pip install -r scripts/requirements-digikala-discovery.txt`; use
   `--chromium-path` / `--headful` / `--batch-size`).
2. **Import CLI** — `scripts/digikala.py`: `validate --mapping ...`, then
   `listings --mapping ...` and `details --listing ...`.
3. **Admin import** — importing service queues listing/import jobs consumed by the Celery
   `digikala` queue (concurrency one). There is no per-job cap on unique imported
   products.

## Migrations, Seeds, And Tests

- Create migrations for every model or persisted-invariant change.
- Never edit an applied migration to change current behavior; add a new migration.
- Pair data normalization with database constraints when introducing canonical formats.
- Keep seeders idempotent and clearly development-only.
- The seed command creates location, canonical categories, catalog/inventory reference data, marketplace pricing-strategy reference data, and customer fixtures, but no generated test catalog, admin account, stock, product variants, or notification provider.
- Canonical category IDs start at `1001`; category seeding updates those IDs without deleting pre-existing categories.

Run focused tests while developing, then broader tests for shared infrastructure or cross-domain changes. Important suites include:

```bash
python manage.py test core.tests
python manage.py test domains.customer.tests
python manage.py test domains.notifications.tests
python manage.py test domains.catalog.tests
python manage.py test domains.catalog.tests_storefront_search
python manage.py test domains.importing.tests.test_digikala_import
python manage.py test domains.inventory.tests
python manage.py test domains.marketplace.tests
python manage.py test domains.files.tests
python manage.py test domains.location.tests
python manage.py test domains.users.tests
```

Confirmed-request tests require Redis. Mock external delivery boundaries, not domain rules or database invariants.

## Environment

Django loads `back/.env` for direct local execution. Use `.env.example` as the variable inventory and never commit real values.

Important groups:

- PostgreSQL: `POSTGRES_*`
- Redis: `REDIS_HOST`, `REDIS_PORT`, `BACKEND_REDIS_PASSWORD`
- Shared cache: Redis database `/0`, with `CACHE_PUBLIC_PREFIX` and `CACHE_PRIVATE_PREFIX`
- Celery: authenticated `backend` user on Redis database `/1`, with `backend:*` keys
- Confirmation: authenticated `backend` user on Redis database `/2`, with `backend:*` keys
- Development confirmation: `CONFIRMED_REQUEST_DEV_MODE`, `CONFIRMED_REQUEST_DEV_CODE`
- Notifications: `NOTIFICATIONS_ALLOW_FAKE_SMS`
- Storage: `STORAGE_BACKEND`, `STORAGE_*`, `FILE_STORAGE_ALIASES`

`MONGO_*` variables are present in the workspace environment but are not currently consumed by backend Python code.

## Security And Production Blockers

- `config/settings.py` currently hardcodes `SECRET_KEY`, `DEBUG=True`, and an empty `ALLOWED_HOSTS`; this is not production-safe.
- Debug exception responses may expose stack traces.
- Never enable static confirmation codes or fake SMS in production.
- A real SMS provider adapter does not exist yet.
- Notification cleanup lacks a periodic database sweep fallback.
- Password-reset throttling is phone-based and still needs trusted-proxy-aware IP protection for public exposure.
- File validation has size and MIME classification checks but no malware scanning or full content sniffing.
- Treat product and category descriptions as untrusted text.

Do not silently work around these constraints. Address them explicitly when preparing production infrastructure.

## Storefront API Backlog

The customer application still needs stable public contracts for:

- Category navigation and customer-safe filter metadata
- Published product search/list/detail with media, variants, pricing, and availability
- Home merchandising, promotions, featured products, related products, and recommendations
- Reviews and ratings
- Wishlists
- Persisted carts and stock-aware totals
- Delivery quotes, discounts, checkout, orders, and payments
- Order history, tracking, cancellation, returns, and refunds
- Customer token refresh and revocation

Agree on domain ownership, publication rules, authorization, and response contracts before implementing these APIs. Do not expose administrative catalog serializers directly to the storefront.

## Validation And Git

For backend changes, run the narrowest relevant tests plus:

```bash
python manage.py check
git diff --check
```

Run migrations and integration checks through the workspace stack when behavior depends on PostgreSQL, Redis, Celery, storage, or Nginx.

Do not commit `.env`, credentials, generated runtime files, or local database artifacts. Commit and push this submodule before committing an updated pointer in the workspace repository. The local scraper under `./script_space/digikala/` is not a tracked path or submodule; keep it out of the repo and commit only `back/` changes.
