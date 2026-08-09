# Wishlist API

Base URL: `/api/wishlist`. All endpoints require a **customer JWT** (`Authorization:
Bearer <access>`). Admin/staff tokens are rejected.

A wishlist is a lightweight "save for later" marker. Product availability is never
checked: unavailable, inactive, or out-of-stock products can still be saved, and
saved products may later become unavailable without being removed. The wishlist
never reserves inventory.

Every response uses the standard envelope:

```json
{ "success": true, "message": "", "data": null, "errors": null }
```

All list responses are paginated (default `page_size` = 20, `?page=N`).

## Models

- `Wishlist`: `id`, `customer_id`, `product_id`, `created_at`.
- A customer may not add the same product twice (unique `customer + product`).

## Endpoints

### List wishlist items

```
GET /api/wishlist/?page=<n>
```

200 response `data`:

```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1,
      "product_id": 12,
      "product": {
        "id": 12,
        "slug": "product-name",
        "name": "Product Name",
        "status": "active",
        "brand": { "id": 3, "name": "Brand" },
        "category": { "id": 5, "name": "Category" }
      },
      "created_at": "2026-08-09T12:00:00Z"
    }
  ]
}
```

Stock and availability are not included; use the storefront product detail for
live availability/pricing.

### Add product

```
POST /api/wishlist/
Content-Type: application/json

{ "product_id": 12 }
```

- 201 on success (returns the created item, same item shape as the list).
- `400` if the product does not exist or is already in the wishlist.

```json
{
  "success": false,
  "errors": { "product_id": ["This product is already in your wishlist."] }
}
```

### Check existence

```
GET /api/wishlist/exists?product_id=12
```

```json
{ "success": true, "data": { "product_id": 12, "in_wishlist": true } }
```

### Remove product

```
DELETE /api/wishlist/products/<product_id>
```

- `200` envelope on success.
- `404` if the item does not exist for this customer.

## State summary

An item is either present or absent; there are no intermediate wishlist states.
The `created_at` timestamp is preserved; re-adding after removal creates a new row.