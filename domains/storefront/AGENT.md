# Storefront Domain

## Purpose

Storefront is responsible for exposing and composing customer-facing data for platform and business storefronts.

It acts as the customer-facing presentation layer of Charchu's backend.

## Responsibilities

Storefront owns:

- Storefront layout and configuration APIs.
- Storefront header and footer data.
- Customer-facing category navigation.
- Storefront homepage APIs.
- Customer-facing product listing and filtering APIs.
- Customer-facing product detail APIs.
- Storefront-specific visibility and presentation rules.
- Storefront-related caching.
- Platform and business storefront context resolution.

## Architectural Boundaries

```text
       ┌────────────────────────────────────────────────────────┐
       │                   Storefront Domain                    │
       │  (Customer Presentation Layer: Layout, Home, Listing,   │
       │   Product Detail, Nav, Tenant Resolution, Presentation)│
       └───────────┬───────────────────┬──────────────────┬─────┘
                   │                   │                  │
                   ▼                   ▼                  ▼
          ┌─────────────────┐ ┌─────────────────┐ ┌───────────────┐
          │ Catalog Domain  │ │ Inventory Domain│ │  Marketplace  │
          │ (Entities, Cat  │ │ (Stock, Units,  │ │  (Pricing,    │
          │  Taxonomy, Mgmt)│ │  Warehouses)    │ │   Workflows)  │
          └─────────────────┘ └─────────────────┘ └───────────────┘
```

### Catalog
- Owns product and category data.
- Owns product and category management logic.
- Storefront must reuse Catalog services/selectors rather than duplicate catalog business logic.

### Marketplace
- Owns marketplace business operations.
- Owns orders and related marketplace workflows.
- Storefront must not duplicate these responsibilities.

### Inventory
- Owns inventory and stock management.
- Storefront can consume inventory information through existing domain interfaces when needed.

## Multi-Tenant Awareness

Storefront supports two contexts:

1. **Platform storefront** (root domain).
2. **Business storefront** (business subdomain).

### Tenant Resolution Rules

- Use existing tenant resolution conventions.
- The authoritative tenant header convention is:
  ```http
  X-Tenant-Subdomain
  ```
- Do not introduce alternative tenant header names.
- Tenant context is resolved via `TenantMiddleware` (`request.business` / `request.business_id`).
- Business-specific data must always be strictly scoped to the resolved business.
- **An unknown business must never silently fall back to platform data.** If a tenant header is provided but cannot be resolved to an active business, the request must fail with an appropriate client error (e.g., HTTP 404), never silently serving platform data.

## Development Guidelines

- **Layered Architecture:** Follow the standard backend flow:
  `Request -> View -> Serializer -> Domain Service -> Infrastructure / External Domains`.
- **Services:** Keep business and composition logic inside services. Services must accept domain primitives or model instances, not DRF `Request` or `Response` instances.
- **Views & Serializers:** Keep request/response handling, input validation, and envelope formatting inside views and serializers according to project conventions.
- **Model Ownership:** Avoid cross-domain model ownership. Do not directly mutate models owned by Catalog, Inventory, Marketplace, or other domains.
- **Reuse Interfaces:** Call public domain services and selectors instead of querying or altering external domain internals directly.
- **Circular Imports:** Guard against circular dependencies across domains. Storefront imports from domain services, while underlying domains should not depend on Storefront.
- **Standard Envelope:** Always use the standard API response helpers (`api_response(...)` from `core.responses`).
- **Caching:** Follow existing caching conventions (`CacheService` / Redis public vs. private caches) with clear cache invalidation strategies and explicit TTLs.
- **Clean & Minimal:** Keep code modular and maintainable. Avoid premature abstractions or empty placeholder files without clear architectural purpose.
- **Testing:** Write comprehensive automated tests for all views, serializers, and services.
