# PreOrder API

Base URL: `/api/preorder`. All endpoints require a **customer JWT** (`Authorization:
Bearer <access>`); admin/staff tokens are rejected.

A pre-order records a customer's interest in a product that currently cannot be
bought but is flagged as **pre-orderable**. Pre-ordering never reserves inventory
and never auto-removes existing entries when a product's status later changes.
It is forward-counted for later offers/notifications when stock arrives.

Pre-orderable products are the catalog products whose status is `preorder`
(ProductStatus seeded by `python manage.py seed`). Only these can be added.

## Endpoints

### List pre-order items

```
GET /api/preorder/?page=<n>
```

200 `data`:

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
        "status": "preorder",
        "brand": { "id": 3, "name": "Brand" },
        "category": { "id": 5, "name": "Category" }
      },
      "created_at": "2026-08-09T12:00:00Z"
    }
  ]
}
```

### Add product

```
POST /api/preorder/
{ "product_id": 12 }
```

- `201` on success.
- `400` if: product missing, already in the list, or **not pre-orderable**.

```json
{ "success": false, "errors": { "product_id": ["This product is not available for pre-order."] } }
```

### Check existence

```
GET /api/preorder/exists?product_id=12
```

```json
{ "success": true, "data": { "product_id": 12, "in_preorder": true } }
```

### Remove product

```
DELETE /api/preorder/products/<product_id>
```

- `200` envelope on success; `404` if not present for this customer.

## Rules / state

- Adding requires `product.status == "preorder"` at add time.
- Duplicates are rejected; only one entry per `(customer, product)`.
- Later status changes never remove existing entries.
- Removal is always allowed by the customer.