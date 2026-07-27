# UzShop Backend - AGENTS.md

## Project

UzShop's Django REST API backend. It serves the separate Next.js admin panel and is organized into business domains with a service layer for business logic.

## Tech Stack

- Python 3.12
- Django 5.2
- Django REST Framework
- SimpleJWT authentication
- PostgreSQL
- Redis and MongoDB infrastructure
- Gunicorn for production serving
- django-unfold for the Django admin

## Commands

Run these commands from `back/` unless stated otherwise.

| Command | What it does |
|---|---|
| `pip install -r requirements.txt` | Install dependencies |
| `python manage.py runserver` | Start the development server |
| `python manage.py migrate` | Apply database migrations |
| `python manage.py makemigrations` | Create migrations after model changes |
| `python manage.py seed` | Seed reference data and temporary catalog development fixtures |
| `python manage.py test` | Run Django tests |
| `python manage.py test domains.catalog.tests` | Run the focused catalog API tests |
| `python manage.py makemessages -l fa -l en` | Update translation message files |
| `python manage.py compilemessages` | Compile translations |

## Architecture

### Key Directories

- `config/` - Django settings, root URLs, ASGI, and WSGI entry points
- `core/` - shared middleware, API responses, exceptions, constants, services, and utilities
- `domains/` - business domains and their application code
- `locale/` - Persian and English translations
- `docs/` - API documentation

### Domains

- `catalog/` - product catalog concerns
- `customer/` - customer accounts and customer JWT authentication
- `inventory/` - stock and inventory concerns
- `location/` - location data and related logic
- `users/` - administrative users and permissions

Keep domain-specific code inside its domain. Put genuinely shared infrastructure in `core/`; do not move business logic into `core/` merely because multiple callers use it.

## Domain Layer Rules

Use this dependency flow:

```text
Request -> View -> Serializer -> Domain Service -> Model/Infrastructure
```

### Views

Views manage the HTTP boundary only:

- Authenticate the caller and enforce permissions.
- Parse request data and invoke serializer validation.
- Call the appropriate domain service with validated plain values.
- Serialize the result and return the standard API response.

Do not put business workflows or direct cross-domain data changes in views.

### Serializers

- Validate request shape, field types, and HTTP-facing input constraints.
- Represent domain objects in API responses.
- Leave business rules and multi-step workflows to services or models.

### Services

- Services are the primary location for domain business logic.
- Use services for workflows, multi-model operations, reusable actions, and coordination between domains.
- Wrap operations that must succeed together in `transaction.atomic()`.
- Accept plain values, validated data, model instances, or an acting user as appropriate.
- Do not accept DRF `Request` objects or return DRF `Response` objects.
- Do not create service wrappers for trivial ORM operations unless they enforce a rule or provide a stable domain API.

### Models

- Models define persisted domain data and relationships.
- Enforce invariants at the model or database level when they must hold regardless of the caller.
- Keep request and response concerns out of models.

### Cross-Domain Work

- Call the target domain's public service instead of directly changing its models.
- Keep dependencies between domains one-directional where possible.
- Avoid circular imports and mutually dependent domain services.
- For complex or reusable read operations, use a query/selector service; simple local reads do not require unnecessary abstraction.

## API Conventions

Root routes currently include:

- `/admin/`
- `/api/users/`
- `/api/customer/`
- `/api/catalog/`

Use `core.responses.api_response` so API responses retain this envelope:

```json
{
  "success": true,
  "message": "",
  "data": null,
  "errors": null
}
```

- Customer and admin JWTs include a `user_type` claim and use separate authentication classes.
- API access is authenticated by default.
- Default pagination is page-number pagination with a page size of 20.
- Exceptions are normalized by `core.exceptions.custom_exception_handler`.

Paginated endpoints keep pagination inside the standard envelope's `data` field:

```json
{
  "success": true,
  "message": "",
  "data": {
    "count": 100,
    "next": null,
    "previous": null,
    "results": []
  },
  "errors": null
}
```

### Catalog Lists

Category and product list endpoints use page-number pagination and accept DRF-style server ordering:

- Ascending: `?ordering=name`
- Descending: `?ordering=-name`
- Pagination: `?page=2`

Category list: `GET /api/catalog/categories`

- Filters: `name`, `status_id`
- Ordering fields: `id`, `name`, `parent_name`, `status_name`
- Status options: `GET /api/catalog/category-statuses`

Category detail list: `GET /api/catalog/category-details`

- Filters: `name`, `type`
- Ordering fields: `id`, `name`, `type`, `required`, `filterable`

Product list: `GET /api/catalog/products`

- Filters: `name`, `category_id`, `status_id`
- Ordering fields: `id`, `name`, `category_name`, `status_name`, `variant_count`

Views parse request query parameters, apply pagination, serialize results, and return `api_response`. Domain services own filter querysets, allowlisted ordering, related-object loading, and annotations. Do not move these queryset rules into frontend code or duplicate them in views.

`CatalogModelPermissions` supports APIViews that declare a `model` attribute. Category status options require `catalog.view_category` so a user who can list categories can also populate the list filter.

### Catalog Write Workflows

Category and category-detail names are globally unique after case/outer-whitespace normalization. The services also collapse repeated internal whitespace before writing. Keep friendly service validation and database constraints aligned when changing name rules.

Category writes:

- Create: `POST /api/catalog/categories`
- Partial update: `PATCH /api/catalog/categories/{id}`
- Similar-name check: `GET /api/catalog/categories/name-suggestions?name=...&exclude_id=...`
- Parent is optional (`null` for a root); updates reject self-parenting and descendant cycles.
- Exact normalized duplicates are rejected; fuzzy matches are warnings supplied to the admin panel.

Category-detail definition writes:

- Create: `POST /api/catalog/category-details`
- Partial update: `PATCH /api/catalog/category-details/{id}`
- Similar-name check: `GET /api/catalog/category-details/name-suggestions?name=...&exclude_id=...`
- Types are `text`, `number`, and `select`.
- Select definitions require comma-separated options; options are normalized before storage.
- Text and number definitions always store `options=""`.

Category-to-detail assignments use one specialized resource:

- Read picker state: `GET /api/catalog/categories/{id}/assign-details`
- Replace assignments: `POST /api/catalog/categories/{id}/assign-details` with `{ "details": [1, 2] }`
- Both methods require `catalog.assign_details_to_category`.
- GET returns the complete assignment snapshot plus filtered/paginated candidates with `assigned` and `in_use` flags.
- POST requires the `details` key, performs an atomic full replacement, and returns the canonical final assignments.
- Details used by products or variants cannot be deassigned. Preserve the category/relationship locks and server-side check when changing this workflow.
- The relationship's legacy `value` is not part of the current assignment UI; new assignments store an empty value.

### Product Creation

The admin product wizard keeps draft data client-side and submits once, so product and initial detail values are created atomically:

- Form options: `GET /api/catalog/product-form-options`
- Category-derived fields: `GET /api/catalog/product-detail-definitions?category_ids=1`
- Atomic creation: `POST /api/catalog/products/create`
- All three endpoints require `catalog.add_product`.

The create payload uses plural `category_ids` deliberately, but validation currently requires exactly one category because `Product.category` remains a foreign key. Keep category-dependent logic behind `ProductService` methods so a future many-to-many migration does not require rewriting views or frontend state.

Product creation validates that:

- Submitted details are assigned to the selected category.
- Every required definition has a nonblank value.
- Number values parse as numbers.
- Select values match the definition's options.
- `(product, detail)` remains unique at the database level.

Descriptions currently store Markdown/plain text, not trusted HTML. Do not render them as HTML without adding server-side sanitization.

### Development Reloading

Docker bind-mounts backend source, but Gunicorn does not auto-reload it. After changing URLs, views, serializers, or services, run `docker compose restart django` from the workspace root before browser/proxy verification. A stale worker can return HTML 404 pages for newly added routes.

## Internationalization

- Default language: Persian (`fa`)
- Supported languages: Persian and English
- `core.middleware.language.HeaderLanguageMiddleware` selects the request language.
- Translation files live under `locale/`.

## Environment

Django loads `back/.env`. The repository-level `.env.example` documents these variables:

- `DEBUG`, `SECRET_KEY`
- `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, `POSTGRES_PORT`
- `REDIS_HOST`, `REDIS_PORT`
- `MONGO_HOST`, `MONGO_PORT`, `MONGO_USER`, `MONGO_PASSWORD`

Never commit secrets or local `.env` files.

## Development Data

The current local development database has this testing superadmin:

- Username: `admin`
- Email: `admin@uzshop.local`
- Password: `Admin123!`
- Admin login endpoint: `POST /api/users/login`

This account is for local testing and development only. Do not use these credentials in staging or production. The account is created directly in the local database and is not part of the seed command or source code.

After creating a fresh database, run migrations and seed the reference data before testing:

```bash
python manage.py migrate
python manage.py seed
```

The current category seeder idempotently creates 10 temporary root categories and 90 temporary child categories for admin-panel development. Names use `Test Category 001` through `Test Category 100`, and active/inactive/pending statuses are distributed across them.

It also creates `Test Detail 001` through `Test Detail 100` across text, number, and select types. A fixed random seed assigns 5–12 details to every temporary category and generates type-appropriate relationship values. Rerunning the seeder replaces only relationships between these temporary categories and details, producing the same dataset each time. Replace all temporary catalog fixtures when final seed data is available.

The product seeder creates active/inactive/pending product statuses and idempotently creates `Test Product 001` through `Test Product 100`. A fixed random seed distributes products across the temporary categories, and statuses are distributed evenly. These products are temporary admin-panel fixtures and do not include variants or stock.

## TODO / Warnings

These are known repository issues. Do not silently work around or fix them during unrelated tasks:

1. `config/settings.py` currently hardcodes `SECRET_KEY` and `DEBUG` rather than using the corresponding environment variables.
2. There is no `back/.env.example`; the available example is at the repository root.

Confirm the intended change with the user before investigating these issues deeply or changing infrastructure configuration.
