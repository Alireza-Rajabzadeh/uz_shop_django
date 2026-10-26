# Business Content Domain — Structure

Reference for how `domains/business_content` is put together. `AGENTS.md` in this
directory states the rules an agent must follow; this document describes the
shape of the code those rules produce.

## Purpose

The domain owns content a **business** owns: its own landing pages and content
pages, each with an independent component vocabulary.

It is the business-scoped counterpart of `domains/content`. Every row belongs to
one `BusinessProfile`; there is deliberately no admin or shared scope here.

| | `domains/content` | `domains/business_content` |
|---|---|---|
| Owner | Platform (admin, shared storefront) | A `BusinessProfile` |
| `business` FK | None | Required (`null=False`) |
| Slug scope | Globally unique | Unique per business |
| Tables | `content_*` | `business_content_*` |
| Contracts file | `data/content_contracts.json` | `data/business_content_contracts.json` |
| Sync command | `sync_content_contracts` | `sync_business_content_contracts` |
| Routes | `/api/content/` | `/api/business-content/` |
| Authoring tier | `admin/*` only | `vendor/*` only |

`Page` and `LandingPage` here are not the `content` models with an extra column.
They are separate rows in separate tables that happen to share a shape. Copying
behaviour across that boundary is a decision, not a default.

## File map

| File | Lines | Role |
|---|---|---|
| `models.py` | 160 | Four models: `LandingPage`, `Page`, `SuggestionPage`, `SEORecord` |
| `contracts.py` | 420 | Contract loading, structural validators, context enforcement |
| `views.py` | 526 | Public delivery views and vendor authoring views |
| `serializers.py` | 224 | `BusinessSlugScopeMixin`, `ContentContextScopeMixin`, eight serializers |
| `services.py` | 172 | `PageService`, `LandingPageService`, `SEOService`, `LandingPageContentResolver`, `public_business_id()` |
| `urls.py` | 61 | Two route groups: public delivery and `vendor/` authoring |
| `signals.py` | 63 | Cache invalidation on save/delete, including the previous slug |
| `cache.py` | 23 | Key builders and `invalidate_*` helpers |
| `admin.py` | 41 | Unfold registration of all four models |
| `data/business_content_contracts.json` | 13 KB | Synced artifact; `contract_version: 4`, 11 components |
| `data/suggestion_pages.py` | 74 | Pure data: eight Persian suggestion rows |
| `tests/test_vendor.py` | 433 | Authoring scoping, SEO scoping, delivery ownership |
| `tests/test_delivery.py` | 384 | Public routes, model-ID resolution, SEO embedding |
| `tests/test_contracts.py` | 292 | Contract file invariants and both validators |
| `tests/test_suggestions.py` | 251 | Suggestion rows, activation, context resolution |
| `tests/test_cache.py` | 138 | Read-through caching and invalidation |
| `tests/factories.py` | 19 | `storefront_business()` — adopts the seeded `id=1` profile |

Wiring:

- `config/urls.py` mounts the domain at `api/business-content/`.
- `apps.py` registers `BusinessContentConfig`, whose `ready()` imports `signals`.
- `config/settings.py` lists `domains.business_content.apps.BusinessContentConfig`.

## Models

`Page` and `LandingPage` share an identical field set and differ only in table,
`related_name`, and page-shaped semantics.

```text
business            FK(business.BusinessProfile, CASCADE, required)
title               CharField(255)
slug                SlugField(allow_unicode)
draft_content       JSONField(default=dict)
published_content   JSONField(default=dict)
status              TextChoices: draft | published | archived
published_at        DateTimeField(null=True)
cache_ttl           PositiveIntegerField(default=300)
created_at / updated_at
```

Constraints:

- `business_content_page_business_slug_unique` on `(business, slug)`
- `business_content_landing_page_business_slug_unique` on `(business, slug)`

Because `business` is `NOT NULL`, one scope constraint per table is enough —
unlike `domains/content`, there is no partial "global slug" constraint.

### `SuggestionPage`

Shared reference data with **no** business FK. It describes what the panel offers
a vendor to create; the per-business artifact is the resulting `Page`.

```text
title, descriptions, required, activate
slug       globally unique (the identity used to match an existing page)
context    page | section | footer
```

Seeded from `data/suggestion_pages.py`: 8 rows — home, about, contact
(`required=True`); faq, terms, privacy, shipping, returns. Re-seeding updates
copy, `required`, and `context` in place by slug while leaving `activate` alone,
so an operator's activation choice survives.

### `SEORecord`

Resource-referencing, with no foreign keys to domain models:

```text
resource_type (landing_page | page), resource_id
unique on (resource_type, resource_id)
title, description, canonical_url, image_id, index, follow, metadata
```

Common SEO values stay as columns; `metadata` is for less common or future
properties. Catalog SEO (product/category/brand) lives in `domains/content`.

## Contract layer

`data/business_content_contracts.json` is a generated artifact, not hand-edited:

```bash
python manage.py sync_business_content_contracts --url <endpoint>
```

`--url` defaults to `BUSINESS_CONTENT_CONTRACTS_URL`, then `CLIENT_PANEL_BASE_URL`,
then `http://localhost:3000/api/content/components`. The file starts as a copy of
the platform vocabulary, so nothing diverges until someone points it elsewhere.

### Components

`contract_version: 4`, 11 components, each declaring `allowedContexts`:

| Component | Allowed contexts |
|---|---|
| `hero_slider` | page, section |
| `product_slider` | page, section |
| `promotional_product_slider` | page, section |
| `small_banner` | page, section |
| `category_grid` | page, section |
| `picture` | page, section |
| `link_list` | page, section, footer |
| `rich_text` | page, section, footer |
| `business_contact` | page, section, footer |
| `social_links` | page, section, footer |
| `category_market_picture` | special |

`special` components are never placed in a slot; dedicated UI calls them
directly. Prop types are drawn from a closed set (`string`, `number`, `integer`,
`boolean`, `color`, `object`, `array`, `model`, `image`, `link`, `rich_text`,
`relative_link`), and `model` props may only reference `products` or `categories`
by ID.

### Context resolution

A row has no `context` column. Its context is the one declared by the
`SuggestionPage` whose slug matches the row's, resolved with `slug__iexact`.
No match falls back to `page`, which every current component allows, so an
arbitrary page is never locked out of its own vocabulary. The panels resolve it
the same way for their picker.

Consequences worth knowing:

- Changing a suggestion's `context` immediately re-scopes every page carrying
  that slug — there is no foreign key and no migration.
- Adding a component never touches the suggestions table; it only edits that
  component's `allowedContexts`.

### Validation chain

```text
validate_contracts_payload   file invariants: envelope keys, unique key/version,
                             non-empty duplicate-free allowedContexts, prop schema
validate_draft_content       document against the file: exact envelope keys,
                             known key/version, unique instance ids, recursive
                             prop typing, required/enum/min_items/max_items
enforce_draft_context        placement: rejects components not allowed for the
                             resolved context, message keeps components[N] shape
```

`enforce_draft_context()` is called from
`ContentContextScopeMixin.validate_draft_content`, so it runs after the
structural validator and sees the payload slug on create or the stored slug on
PATCH. The platform `domains/content` domain validates the same field but does
not enforce it, because it has no row context to resolve.

## API surface

### Public delivery (`AllowAny`, no authentication)

Serves the singleton business: `services.public_business_id()` returns the
lowest-pk `BusinessProfile` (the `inventory.0022` seed, `id=1`, no vendor).

```text
GET /api/business-content/home
GET /api/business-content/pages/<slug>
GET /api/business-content/pages/<slug>/preview
GET /api/business-content/landing-pages/<slug>
GET /api/business-content/landing-pages/<slug>/preview
```

`home` is the `Page` with slug `home` (`PageService.HOME_SLUG`), published only.
The plain routes answer published rows; the `/preview` variants answer drafts.

**Nothing consumes these yet.** The shared storefront still reads
`/api/content/`; these routes exist so a business-branded storefront can be
wired up later.

### Vendor authoring

`VendorJWTAuthentication` + `IsAuthenticated`. The owner is resolved as
`BusinessProfile.objects.filter(vendor=request.user).first()`; a caller only
ever sees its own rows and foreign IDs answer 404. `business` is never read from
the payload — the view assigns it on `save()`.

```text
GET|POST         /api/business-content/vendor/landing-pages
GET|PATCH|DELETE /api/business-content/vendor/landing-pages/<id>
POST             /api/business-content/vendor/landing-pages/<id>/publish
GET              /api/business-content/vendor/landing-pages/<id>/preview
GET|PUT|DELETE   /api/business-content/vendor/landing-pages/<id>/seo
                                       ...same five for /vendor/pages
GET              /api/business-content/vendor/options/products
GET              /api/business-content/vendor/options/categories
GET              /api/business-content/vendor/component-contracts
GET              /api/business-content/vendor/suggestions
```

Notes:

- The `vendor/` prefix exists so `<int:id>` detail routes stay unambiguous
  against the `<str:slug>` delivery routes.
- Lists support an `ordering` allowlist (`id`, `title`, `slug`, `status`,
  `created_at`, `updated_at`, each optionally negated) and page-number pagination.
- Landing-page routes additionally carry `RequiresContentLandingPage`
  (`domains/packages/permissions.py`); plain pages are not gated.
- `publish` promotes `draft_content` into `published_content`, sets `published`,
  and stamps `published_at`.
- `preview` resolves the draft through
  `LandingPageContentResolver.for_authoring()`.
- `options/*` is filtered to the business's registered categories.
- `component-contracts` serves this domain's file, so the editor palette matches
  what `validate_draft_content` accepts here.
- `suggestions` returns active rows in seeded `id` order; `activate` is applied
  server-side and not sent to the panels, while `slug` and `context` are.
- There is no `/admin/*` tier. The admin panel edits platform content under
  `/api/content/admin/`.

## Delivery pipeline

1. **Resolve references.** `LandingPageContentResolver` walks the components,
   collects `model`-typed prop values (`products`, `categories`), batches them
   through `StorefrontProductService.get_content_items` and
   `CategoryService.get_storefront_content_items`, then substitutes IDs with
   objects. Unresolvable IDs are dropped from `many` props and become `null` for
   `one`.

   Three factories: the default (public), `for_authoring()` (includes unlisted
   products via `ProductService.get_authoring_content_items`), and
   `for_preview()` (`include_unlisted=True`).

2. **Cache.** Public responses go through `CacheService.get_or_set_public` under:

   ```text
   business-content:home
   business-content:pages:<slug>
   business-content:landing-pages:<slug>
   ```

   The per-row `cache_ttl` rides along with the payload so one lock-protected
   rebuild decides whether the result is stored at all; `0` disables caching.

3. **Invalidate.** `signals.py` invalidates after commit on save and delete,
   including the **previous** slug captured in `pre_save`, so a rename leaves no
   stale key. `SEORecord` changes resolve back to the page slug and invalidate
   that. A `Page` with slug `home` also clears `business-content:home`.

## Migration history

```text
0001_initial                    LandingPage, Page, SEORecord
0002_suggestionpage
0003_move_stranded_home_landing_page
0004_seed_suggestion_pages      seeds from data/suggestion_pages.py
0005_suggestion_context         drop component_lists, add context, re-seed
```

`0005` is the notable one. The old `component_lists` held a raw component
allow-list per suggestion, which scaled `components × suggestions` and went
stale silently when a component was renamed. Placement moved onto the contract
as `allowedContexts`; a suggestion now declares only *which* placement it is.

## Tests

```bash
python manage.py test domains.business_content
```

`tests/factories.py` provides `storefront_business()`, which adopts the seeded
`id=1` profile. Tests must use it (or pass an explicit pk) rather than a bare
`BusinessProfile.objects.create()`: `inventory.0022` inserts `id=1` directly and
never advances the PK sequence, so a plain `create()` collides with it.

## Observations

These are notes from reading the code, not statements of spec. Confirm intent
before treating any of them as a bug.

1. **Doc drift on `ALLOWED_CONTEXTS`.** `AGENTS.md` lists the set as
   `page, section, footer`, but `contracts.py` also accepts `special`, and
   `SuggestionPage.Context` has no `SPECIAL` choice. The combination is
   consistent in effect — `special` components are never slotted and no
   suggestion can claim it — but the documented set and the enforced set differ.

2. **Unauthenticated draft previews.** `/pages/<slug>/preview` and
   `/landing-pages/<slug>/preview` are `AllowAny` and serve draft content for the
   singleton business. `domains/content` uses the same pattern, so this is a
   pre-existing shared decision rather than a local slip — but it does mean
   unpublished content is publicly readable by slug.

3. **Duplication is intentional.** Two identical models, two near-identical
   services, two near-identical view and serializer sets. If a third page-shaped
   resource appears, an abstract base or a `kind` discriminator is worth
   weighing; today the separation is what keeps the two vocabularies independent.

4. **Package gating is asymmetric.** `RequiresContentLandingPage` protects
   landing pages but not plain pages, so a vendor without the content package
   can still author arbitrary pages. Landing pages appear to be the premium
   surface, but the domain's `AGENTS.md` does not say so.

5. **`public_business_id()` has no fallback.** If the seed row is deleted, or a
   real multi-business deployment arrives, all five public routes silently 404
   rather than erroring. The singleton assumption is acknowledged in `AGENTS.md`
   but no migration path is documented.

## See also

- `AGENTS.md` in this directory — rules and conventions for changing this domain.
- `../content/` — the platform-owned counterpart.
- `../AGENTS.md` — backend-wide layering, API, and testing conventions.
