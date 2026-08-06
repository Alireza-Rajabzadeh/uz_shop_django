# Digikala Catalog Import

The Digikala integration is file-backed and migration-free. The same reusable
Python modules are called by the CLI, Celery tasks, and admin API.

## Pilot Policy

- Up to five approved categories and twenty listing products per category.
- Prices are stored as Iranian rials (`IRR`) without conversion.
- Products are created as `pending`.
- Digikala stock is not imported into UzShop inventory.
- Image URLs remain in the normalized detail JSON; media is not downloaded.
- Existing imported products are identified by `digikala-<product-id>` slug.
- Refreshes update source fields and prices, union categories, and preserve
  local status, stock, media, and data absent from a partial source response.

Generated files live below `DIGIKALA_RUNTIME_ROOT`. Only server-generated UUID
listing files are exposed through the admin API.

## Reusable Commands

Validate approved mappings:

```bash
python scripts/digikala.py validate \
  --mapping core/management/data/digikala_category_mappings.json
```

Generate a listing without the admin page:

```bash
python scripts/digikala.py listings \
  --mapping core/management/data/digikala_category_mappings.json \
  --output /tmp/digikala-listing.json \
  --products-per-category 20 \
  --timeout 30 --retries 3 --delay 1
```

Fetch all normalized product details from a listing:

```bash
python scripts/digikala.py details \
  --listing /tmp/digikala-listing.json \
  --output-dir /tmp/digikala-details
```

Repeat `--product-id` to fetch only selected products.

Category API discovery is intentionally offline and optional because it needs
Playwright and Chromium:

```bash
pip install -r scripts/requirements-digikala-discovery.txt
playwright install chromium
python scripts/digikala.py discover \
  --categories core/management/data/categories.json \
  --category-id 1003 --category-id 1004 \
  --output /tmp/approved-digikala-categories.json
```

Review discovered mappings before replacing the version-controlled approved
mapping file.

## Admin Workflow

The admin page is `/catalog/imports/digikala`.

1. Create an asynchronous listing job from approved categories.
2. Select an immutable generated listing file.
3. Select all products or stage product IDs across pages.
4. Start the asynchronous detail-fetch and import job.
5. Monitor progress, cancel between products, or retry failed products.

The dedicated `digikala` Celery queue runs with concurrency one. Job state,
events, raw detail payloads, normalized detail payloads, and failure results
remain on the shared runtime filesystem so a redelivered task can resume.

## Import Semantics

- Canonical categories are resolved by local ID. Missing selected categories
  and ancestors are recovered only from the controlled canonical manifest.
- Brands use English title or source code for `name` and Persian title for
  `fa_name`; Persian is the final fallback for both.
- Unknown specifications become optional, non-filterable text details.
- Detail/category and variant-attribute/category relations are additive.
- Variant options use deterministic `DK...` SKU codes.
- Seller offers with the same option combination collapse to the lowest-priced
  marketable offer.
- Optionless products receive the controlled `Variant / Default` selection.
- `rrp_price` is the base price and the exact difference from `selling_price`
  is stored as a fixed Rial discount.

An upstream detail-fetch failure produces no database write for that product.
Each product import runs in its own database transaction.
