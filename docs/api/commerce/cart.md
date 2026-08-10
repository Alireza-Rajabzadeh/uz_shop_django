# Cart API

Base URL: `/api/cart`. All endpoints require a **customer JWT**; admin/staff tokens
are rejected. Each customer has exactly one active cart (created on first access).

**The cart never stores prices, discounts, or inventory.** Every read recomputes
from the **current** `ProductVariant` price/discount and live inventory. Cart values
are not historical snapshots — if a price changes, the cart reflects it at the next
read/checkout.

## Address snapshot

`address_info` is a flat snapshot (no relation to `CustomerAddress`). Fields:

```json
{
  "country_id": 1, "country_name": "Iran", "country_fa_title": "",
  "state_id": 2, "state_name": "Tehran", "state_fa_title": "",
  "city_id": 3, "city_name": "Tehran", "city_fa_title": "",
  "postal_code": "158756413",
  "address_line1": "Main St 1", "address_line2": "", "house_number": "",
  "receiver_name": "Hossein",
  "receiver_phone": "09120000000"
}
```

- **Copy from a saved address:** send `saved_address_id` (+ optionally
  `receiver_name`/`receiver_phone`). If the receiver fields are not sent they
  default to the customer's own name and phone. If **only one** of the two is sent,
  the request is rejected — receiver name and phone must be provided together.
- **Manual input:** send the full snapshot: `country_id`, `state_id`, `city_id`,
  `postal_code`, `address_line1`, `address_line2`*, `house_number`*,
  `receiver_name`, `receiver_phone` (`*` optional). The state/country and city/state
  hierarchy is validated server-side.

## Item payload (all reads, computed live)

```json
{
  "id": 1,
  "variant_id": 12,
  "quantity": 2,
  "product_id": 9,
  "product_name": "Product Name",
  "product_status": "active",
  "sku": "CG1-PD9-BLK",
  "combination_key": "3:12|5:9",
  "unit_price": "100.00",
  "discount_type": "percentage",
  "discount_value": "10.00",
  "effective_price": "90.00",
  "unit_discount_amount": "10.00",
  "line_discount": "20.00",
  "line_total": "180.00",
  "inventory_strategy": { "id": 1, "code": "regular", "name": "Regular" },
  "available": 8,
  "selections": [ { "attribute_id": 3, "attribute": "Color", "option_id": 12, "option": "Black" } ],
  "purchasable": true,
  "valid": true,
  "status": "available",
  "reason": "",
  "suggested_action": "none"
}
```

Per-item `status` / `reason` / `suggested_action`:

| status | meaning | `suggested_action` |
|---|---|---|
| `available` | purchasable and stock ≥ quantity | `none` |
| `out_of_stock` | purchasable but quantity > available | `move_to_wishlist` |
| `pre_orderable` | product is now only pre-orderable | `move_to_preorder` |
| `variant_unavailable` | product inactive/deleted or variant gone | `remove` |

`valid=false` items stay visible but **block checkout** until resolved (remove /
move to wishlist / move to pre-order).

## Endpoints

### Get current cart

```
GET /api/cart/
```

`data`: `{ "id", "address_info", "items": [ ... ], "totals": { "subtotal", "discount_amount", "shipping_amount", "total_amount" }, "cart_valid": boolean }`

`subtotal` is the undiscounted total (`unit_price × quantity`); `total = subtotal - discount + shipping` (shipping is always `0.00` for now, no shipping engine yet).

### Add item (create or update quantity)

```
POST /api/cart/items
{ "variant_id": 12, "quantity": 2 }
```

- `quantity` optional (default 1), must be ≥ 1.
- If the variant is already in the cart, the quantity is **replaced** with the sent
  value (no duplicate rows).
- `201` returns the **full current cart** (the `describe_cart` payload above), so
  the client can update its local cart from one response.
- `400` if quantity < 1 or variant does not exist.

### Sync local cart with the backend

```
POST /api/cart/sync
{ "items": [ { "variant_id": 12, "quantity": 2 } ] }
```

Used on cart open to reconcile a client-held (localStorage) cart against the
catalog. For each entry the backend keeps variants that still exist (added/merged
into the server cart with the sent quantity) and reports the ones it could not keep:

```json
{
  "cart": { "...": "describe_cart payload" },
  "removed": [
    { "variant_id": 12, "product_id": null, "product_name": "",
      "reason": "This item no longer exists.", "suggested_action": "remove" }
  ]
}
```

`suggested_action` is one of:

- `remove` — the variant no longer exists (no follow-up possible).
- `wishlist` — the product exists but is no longer purchasable; the client can
  offer to move it to the wishlist.
- `preorder` — the product now requires pre-order; the client can move it to the
  pre-order list.

The client should update its local cart from `cart` and follow up on each
`removed` entry accordingly. Empty `items` returns the current server cart unchanged.

### Update quantity

```
PATCH /api/cart/items/<item_id>
{ "quantity": 5 }
```

`400` for quantity < 1, `404` if the item is not in the customer's cart.

### Remove item

```
DELETE /api/cart/items/<item_id>
```
`200` envelope; `404` if missing.

### Update / copy address

```
PUT /api/cart/address
{ "saved_address_id": 4 }                         // or receiver overrides
{ "country_id":1,"state_id":2,"city_id":3,"postal_code":"...","address_line1":"...","receiver_name":"...","receiver_phone":"..." }
```

`200` with the stored snapshot.

### Move item to wishlist

```
POST /api/cart/items/<item_id>/move-to-wishlist
```

Guarantees the product is in the customer's wishlist (idempotent), then removes the
cart item. `200` `{ "product_id", "moved_to": "wishlist" }`.

### Move item to pre-order

```
POST /api/cart/items/<item_id>/move-to-preorder
```

Only allowed when the product's current status is `preorder`. Adds to the
pre-order list (idempotent), removes the cart item. `400` with
`{"product": [...]}` otherwise (item stays in cart).

### Validate cart before checkout

```
GET /api/cart/validate
```

```json
{
  "valid": true,
  "totals": { "subtotal": "...", "discount_amount": "...", "shipping_amount": "0.00", "total_amount": "..." },
  "items": [
    { "id": 1, "variant_id": 12, "quantity": 2, "product_name": "...", "status": "available", "reason": null, "valid": true, "suggested_action": "none" }
  ]
}
```

`valid` is `false` for an empty cart or when any item is invalid.

## Cart flow (for frontend)

1. `GET /api/cart/` → cart with live prices/state.
2. Add items via `POST /api/cart/items`; adjust with `PATCH /api/cart/items/<id>`.
3. Set address with `PUT /api/cart/address` (saved or manual).
4. Before checkout run `GET /api/cart/validate`.
5. For each invalid item apply its `suggested_action` (`move-to-wishlist`,
   `move-to-preorder`, or removal) and revalidate.
6. Proceed to the Order/checkout API (Step 4) which revalidates everything
   server-side again.