# Business Content Domain

## Purpose

The Business Content domain manages content owned by a business: its own landing pages and content pages, with independent component contracts.

It is a Git submodule directory inside the UzShop backend. Follow the backend conventions in `../AGENTS.md` (domain layering, db_table naming, status patterns, migrations, admin registration) when changing code here.

## How it relates to `domains/content`

This domain is the business-scoped counterpart of `../content`.

| | `content` | `business_content` |
|---|---|---|
| Owner | Platform (admin, shared storefront) | A `BusinessProfile` |
| `business` FK | **None** | Required (`null=False`) |
| Slug scope | Globally unique | Unique per business |
| Tables | `content_*` | `business_content_*` |
| Contracts file | `data/content_contracts.json` | `data/business_content_contracts.json` |
| Sync command | `sync_content_contracts` | `sync_business_content_contracts` |
| Routes | `/api/content/` | `/api/business-content/` |
| Authoring tier | `admin/*` only | `vendor/*` only |

The two domains were split on purpose: business pages may need different components and configuration than the platform storefront. Copying behaviour from one to the other is a decision, not an accident — change both sides deliberately and update both `AGENTS.md` files.

Do **not** re-add a `business` FK to `domains.content`, and do not point either domain at the other's contracts file.

## Current responsibilities

- Business landing pages
- Business content pages
- Business-scoped SEO metadata for those pages
- Draft and published page versions
- An independent component-contract vocabulary

## Domain boundary

```text
BusinessContent
- Page            (business-owned)
- LandingPage     (business-owned)
- SEORecord       (resource-referencing)

Catalog / Inventory / Business
- owned by their own domains
```

`Page` and `LandingPage` here are **not** the `content` models with an extra column — they are separate rows in separate tables that happen to share a shape.

## Ownership rules

- Every row requires a `business`. There is no shared/admin scope.
- Authoring views resolve the owner from `BusinessProfile.objects.filter(vendor=request.user)`; a caller only ever sees its own rows.
- The public delivery routes resolve the owner with `services.public_business_id()`, which reads the lowest-pk profile. `inventory.0022` seeds `BusinessProfile` id=1 with no vendor, and that is the row delivery serves.

## Models

- `Page` — table `business_content_page`. `business` FK (required, `related_name="business_content_pages"`), plus `title`, `slug`, `draft_content` / `published_content` JSON, `status` (`draft` / `published` / `archived`), nullable `published_at`, `cache_ttl`, `created_at`, `updated_at`.
- `LandingPage` — table `business_content_landing_page`, same field shape (`related_name="business_content_landing_pages"`).
- `SEORecord` — table `business_content_seo_record`. Resource-referencing (`resource_type` + `resource_id`), unique on that pair. `resource_type` is `landing_page` or `page`, addressing rows in *this* domain's tables only.

Constraints:

- `business_content_landing_page_business_slug_unique` on `(business, slug)`
- `business_content_page_business_slug_unique` on `(business, slug)`
- `business_content_seo_resource_unique` on `(resource_type, resource_id)`

`business` is NOT NULL, so unlike `content` there is no partial "global slug" constraint.

## Component contracts

`data/business_content_contracts.json` is a **synced artifact**, not hand-edited:

```bash
python manage.py sync_business_content_contracts --url <endpoint>
```

`--url` defaults to `BUSINESS_CONTENT_CONTRACTS_URL`, then `CLIENT_PANEL_BASE_URL`, then `http://localhost:3000/api/content/components`. Point it at a different endpoint (or edit the file directly) to give business pages their own vocabulary — the file starts as a byte-for-byte copy of the platform one, so nothing diverges until you do.

`contracts.py` validates the file itself (`validate_contracts_payload`) and authored documents against it (`validate_draft_content`). If you diverge the vocabulary, `tests/test_contracts.py` pins the current component list and must be updated in the same change.

## Public delivery

Mounted under `/api/business-content/`.

- `GET /api/business-content/home` — the business home `Page` (`PageService.HOME_SLUG`), published only; 404 otherwise.
- `GET /api/business-content/pages/<slug>` / `.../preview` — published / draft-by-slug.
- `GET /api/business-content/landing-pages/<slug>` / `.../preview` — published / draft-by-slug.

Nothing currently consumes these: the shared storefront still reads `/api/content/`. They exist so a business-branded storefront can be wired up later.

Public responses are cached with `CacheService` under `business-content:*` keys, honouring per-row `cache_ttl` (`0` disables). `signals.py` invalidates on save/delete, including the previous slug after a rename.

## Business (vendor) API

Mounted under `/api/business-content/vendor/`, JWT vendor auth + `IsAuthenticated`. The `vendor/` prefix keeps `<int:id>` detail routes unambiguous against the `<str:slug>` delivery routes.

- `GET|POST /api/business-content/vendor/landing-pages` and `.../pages` — list (ordering allowlist, paged) / create.
- `GET|PATCH|DELETE .../<id>` — retrieve / update / delete, always scoped to the caller's business; foreign rows 404.
- `POST .../<id>/publish` — promote `draft_content` into `published_content`, set `published`, stamp `published_at`.
- `GET .../<id>/preview` — resolve `draft_content` through `LandingPageContentResolver.for_authoring()`.
- `GET|PUT|DELETE .../<id>/seo` — the page's `SEORecord`.
- `GET /api/business-content/vendor/options/products|categories` — picker options, filtered to the business's registered categories.
- `GET /api/business-content/vendor/component-contracts` — this domain's vocabulary.

There is no `/admin/*` tier: the admin panel edits platform content under `/api/content/admin/`.

## Conventions to preserve

- `db_table = "business_content_<table>"`, `TextChoices` status, `created_at`/`updated_at`, admin registration in `admin.py`.
- Keep common SEO values as columns; use `metadata` only for less common/future properties.
- `SEORecord` stays resource-referencing — no foreign keys to domain models.
- Slug scoping is per business and enforced both by the DB constraint and by `BusinessSlugScopeMixin.validate_slug` (which keeps duplicates a 400 instead of an `IntegrityError`). `business` is never read from the payload; the view assigns it on `save()`.

## Tests

```bash
python manage.py test domains.business_content
```

- `tests/test_vendor.py` — authoring scoping, SEO scoping, delivery ownership.
- `tests/test_delivery.py` — public routes, resolution of component model IDs, SEO embedding.
- `tests/test_contracts.py` — the synced file's invariants and both validators.
- `tests/test_cache.py` — read-through caching and invalidation.
- `tests/factories.py` — `storefront_business()`, which adopts the seeded id=1 profile. Tests must use it (or an explicit pk) rather than a bare `BusinessProfile.objects.create()`: `inventory.0022` inserts id=1 directly and never advances the PK sequence, so a plain `create()` collides with it.
