# Content Domain

## Purpose

The Content domain manages public-facing content and presentation configuration.

It is a Git submodule directory inside the UzShop backend. Follow the backend conventions in `../AGENTS.md` (domain layering, db_table naming, status patterns, migrations, admin registration) when changing code here.

## Current responsibilities

- Platform landing pages
- Platform content pages (including the storefront `home`)
- Landing-page component configuration
- Draft and published page versions
- Reusable SEO metadata, including SEO for catalog resources

## Scope: platform only

This domain serves the shared, admin-owned storefront. Its models carry **no**
`business` foreign key — a row belongs to the platform, and `business`-scoped
content lives in the sibling `../business_content` domain, which owns its own
tables, contracts file, and `/api/business-content/` routes.

Do not re-add a `business` field here, and do not move `Page` or `LandingPage`
back behind a business scope.

## Future responsibilities (planned)

- Blog posts
- Blog categories
- Blog tags
- Other editorial/public content

## Domain boundary

Content owns presentation and editorial content.

It does **not** own business entities belonging to other domains.

```text
Catalog
- Product
- Category
- Brand

Inventory
- Stock
- Inventory rules

Content (platform scope)
- Page
- LandingPage
- SEORecord
- BlogPost (future)

BusinessContent (business scope)
- Page
- LandingPage
- SEORecord
```

A Product can have an SEO record:

```text
resource_type = product
resource_id = <product id>
```

but the Product still belongs to the Catalog domain. The SEO record only provides SEO overrides and presentation metadata.

## Pages

The homepage is a normal `Page` with slug:

```text
home
```

resolved by `PageService.HOME_SLUG`.

Page content is component-driven and stored as JSON.

- Admins edit `draft_content`.
- Preview uses `draft_content`.
- Publishing copies/promotes the draft into `published_content`.
- Normal client requests only use `published_content`.

The client application is responsible for mapping component types from the JSON structure to actual client-side components and rendering them with the client theme.

Public storefront access:

- `GET /api/content/home` — the storefront home page. Resolves the `Page` with slug `home` (`PageService.HOME_SLUG`) and requires it to be `published`; otherwise 404. Returns the resolved `published_content`.
- `GET /api/content/pages/<slug>` — published page by slug.
- `GET /api/content/pages/<slug>/preview` — draft/preview page by slug.
- `GET /api/content/landing-pages/<slug>` — published landing page by slug.
- `GET /api/content/landing-pages/<slug>/preview` — draft/preview landing page by slug.
- `GET /api/content/seo/<resource_type>/<slug>` — public identity + SEO for `brand` and `category` only.

Keep these boundaries in mind when adding future Content-domain features.

## Models

- `Page` — table `content_page`. Fields: `title`, globally unique `slug` (unicode-allowed), `draft_content` / `published_content` JSON, `status` (`draft` / `published` / `archived`), nullable `published_at`, `cache_ttl`, `created_at`, `updated_at`.
- `LandingPage` — table `content_landing_page`. Same field shape as `Page`.
- `SEORecord` — table `content_seo_record`. Resource-referencing model (no FKs to Product, Category, etc.): `resource_type` + `resource_id`, common SEO columns (`title`, `description`, `canonical_url`, `image_id`, `index`, `follow`), plus `metadata` JSON for extensibility. Unique on `resource_type + resource_id`.

## Conventions to preserve

- Keep common SEO values (`title`, `description`, `canonical_url`, `image_id`, `index`, `follow`) as columns; use `metadata` only for less common/future SEO properties. Do not add a column for every future SEO field, and do not move the common fields into JSON.
- `SEORecord` must remain resource-referencing: do not add foreign keys from SEO to domain models. Add `BlogPost` as its own Content model when the time comes.
- Use the existing model patterns: `db_table = "content_<table>"`, `TextChoices` status, `created_at`/`updated_at`, and admin registration in `admin.py`.
- Slug uniqueness here is global (`content_landing_page_slug_unique`, `content_page_slug_unique`). Per-business slug scoping belongs in `business_content`.
- API-facing messages (`ValidationError`, `NotFound`, `api_response(message=...)`) go through `gettext()` with an **English** msgid and a Persian msgstr in `locale/fa/LC_MESSAGES/django.po`. After adding one, run `python manage.py makemessages -l fa -l en` and `python manage.py compilemessages`. Never leave a `#, fuzzy` flag on an entry: `msgfmt` skips fuzzy entries so the message silently falls back to English, and the msgstr underneath is `msgmerge`'s guess — usually an unrelated string. `domains/business_content/contracts.py` is a deliberate copy of this one; localise both together.

## Admin API

Mounted under `/api/content/`. There is deliberately no `vendor/` tier here; business authoring moved to `/api/business-content/vendor/`.

- `GET|POST /api/content/admin/landing-pages` — list / create landing pages. Exposed by `AdminLandingPageList` in `views.py` (JWT admin auth + `AdminModelPermissions`, so `content.view_landingpage` / `content.add_landingpage`). Serialization via `LandingPageSerializer`.
- `GET|PATCH|DELETE /api/content/admin/landing-pages/<id>` — retrieve / update / delete a landing page (`AdminLandingPageDetail`). Delete requires `content.delete_landingpage`.
- `POST /api/content/admin/landing-pages/<id>/publish` — promote `draft_content` to `published_content`, set status to `published`, and stamp `published_at` (`AdminLandingPagePublish`, requires `content.change_landingpage`).
- `GET|POST /api/content/admin/pages`, `GET|PATCH|DELETE /api/content/admin/pages/<id>`, `POST /api/content/admin/pages/<id>/publish` — the `Page` equivalents, requiring `content.view_page` / `content.add_page` / `content.change_page` / `content.delete_page`.
- `GET|PUT|DELETE /api/content/admin/landing-pages|pages|products|categories|brands/<id>/seo` — per-resource SEO. Catalog resources require `catalog.change_product` / `catalog.change_category` / `catalog.change_brand`.
- `GET /api/content/admin/component-contracts` — the synced component vocabulary used by the editor.
- `GET /api/content/admin/options/products|categories` — paginated picker options for component `model` props.

## Contracts

`data/content_contracts.json` is a **synced artifact**, not hand-edited:

```bash
python manage.py sync_content_contracts --url <endpoint>
```

`contracts.py` validates both the contract file itself (`validate_contracts_payload`) and authored documents against it (`validate_draft_content`). The `business_content` domain syncs its own independent copy via `sync_business_content_contracts`; the two vocabularies may diverge.

Every synced component carries `allowedContexts` — a non-empty, duplicate-free subset of `ALLOWED_CONTEXTS` (`page`, `section`, `footer`) — beside `key`, `name`, `version`, `description`, and `props`. Both domains validate the field identically because both files come from the same panel source, but only `business_content` *enforces* it against a row; this domain has no row context to resolve. Keep `ALLOWED_CONTEXTS` in step with `domains/business_content/contracts.py` and with `ContentContext` in the panels.
