# Content Domain

## Purpose

The Content domain manages public-facing content and presentation configuration.

It is a Git submodule directory inside the UzShop backend. Follow the backend conventions in `../AGENTS.md` (domain layering, db_table naming, status patterns, migrations, admin registration) when changing code here.

## Current responsibilities

- Landing pages
- Landing-page component configuration
- Draft and published page versions
- Reusable SEO metadata

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

Content
- LandingPage
- SEORecord
- BlogPost (future)
```

A Product can have an SEO record:

```text
resource_type = product
resource_id = <product id>
```

but the Product still belongs to the Catalog domain. The SEO record only provides SEO overrides and presentation metadata.

## Landing pages

Landing pages are generic configurable client pages.

The homepage is implemented as a normal landing page with slug:

```text
home
```

Landing-page content is component-driven and stored as JSON.

- Admins edit `draft_content`.
- Preview uses `draft_content`.
- Publishing copies/promotes the draft into `published_content`.
- Normal client requests only use `published_content`.

The client application is responsible for mapping component types from the JSON structure to actual client-side components and rendering them with the client theme.

Keep these boundaries in mind when adding future Content-domain features.

## Models

- `LandingPage` — table `content_landing_page`. Fields: `title`, unique `slug` (unicode-allowed), `draft_content` / `published_content` JSON, `status` (`draft` / `published` / `archived`), nullable `published_at`, `created_at`, `updated_at`.
- `SEORecord` — table `content_seo_record`. Resource-referencing model (no FKs to Product, Category, etc.): `resource_type` + `resource_id`, common SEO columns (`title`, `description`, `canonical_url`, `image_id`, `index`, `follow`), plus `metadata` JSON for extensibility. Unique on `resource_type + resource_id`.

## Conventions to preserve

- Keep common SEO values (`title`, `description`, `canonical_url`, `image_id`, `index`, `follow`) as columns; use `metadata` only for less common/future SEO properties. Do not add a column for every future SEO field, and do not move the common fields into JSON.
- `SEORecord` must remain resource-referencing: do not add foreign keys from SEO to domain models. Add `BlogPost` as its own Content model when the time comes.
- Use the existing model patterns: `db_table = "content_<table>"`, `TextChoices` status, `created_at`/`updated_at`, and admin registration in `admin.py`.

## Admin API

Mounted under `/api/content/`.

- `GET|POST /api/content/admin/landing-pages` — list / create landing pages. Exposed by `AdminLandingPageList` in `views.py` (JWT admin auth + `AdminModelPermissions`, so `content.view_landingpage` / `content.add_landingpage`). Serialization via `LandingPageSerializer`.
- Currently only list + create are implemented. `published_at`, `published_content`, and draft→publish promotion, edit, delete, and preview are not wired yet. Keep the split between `draft_content` (admin edits) and `published_content` (client-facing) when adding them.
