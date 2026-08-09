# Order & Payment API

Base URL: `/api/order`. All endpoints require a **customer JWT**; admin/staff tokens
are rejected.

Order lifecycle:

```
payment_waiting --(manual payment confirmed)--> success
       │
       ├--(customer cancel)--------------------> failed
       └--(reservation expired)----------------> expired
```

`successful_payment`/`payments` show the accounting record. `online` and `credit`
payment methods are seeded as available for the future, but the only working
pay flow is **manual** (`card_to_card`, `deposit_to_account`).

## Checkout

```
POST /api/order/
```

Creates an order from the current authenticated customer's **cart**, then empties
the cart. Server-side:

1. Cart must have a delivery address (`PUT /api/cart/address` first).
2. Every item is revalidated against live product status, price, discount, and
   inventory availability.
3. Prices/totals are recomputed from the current `ProductVariant` — nothing is
   trusted from the frontend.
4. Stock is reserved atomically under row locks:
   - **normal** strategy: `reserved` incremented on the default warehouse stock row.
   - **serialized** strategy: concrete serial rows are flipped to `reserved`.
5. `reservation_expires_at = now + ORDER_RESERVATION_MINUTES` (default 30).

`201` returns the full order payload (starts in `payment_waiting`).

`400` `{ "address": [...] }` if no address, `{ "cart": [...] }` if empty,
`{ "items": [...] }` listing each problematic SKU otherwise.

## Order payload

```json
{
  "id": 1,
  "status": "payment_waiting",
  "address_info": { "...cart address snapshot..." },
  "items": [
    {
      "id": 1,
      "variant_id": 12,
      "sku": "CG1-PD9-BLK",
      "product_id": 9,
      "product_name": "Product Name",
      "combination_key": "3:12|5:9",
      "quantity": 2,
      "unit_price": "100.00",
      "discount_type": "percentage",
      "discount_value": "10.00",
      "discount_amount": "20.00",
      "final_price": "180.00",
      "inventory_strategy": { "id": 1, "code": "normal" },
      "selections": [ { "attribute_id": 3, "attribute": "Color", "option_id": 12, "option": "Black" } ]
    }
  ],
  "totals": {
    "subtotal": "200.00",
    "discount_amount": "20.00",
    "shipping_amount": "0.00",
    "total_amount": "180.00"
  },
  "reservation_expires_at": "2026-08-09T...",
  "successful_payment": null,
  "payments": [],
  "created_at": "2026-08-09T..."
}
```

`items` are a historical **snapshot** (`variant_info`), so order data survives later
catalog/inventory changes. Line `final_price` = effective (discounted) unit price ×
qty; `discount_amount` is the line discount.

## List / detail

```
GET /api/order/
GET /api/order/<order_id>
```

List returns `{ "count", "results": [ order, ... ] }` newest-first. Both lazily expire
`payment_waiting` orders whose `reservation_expires_at` has passed, releasing their
stock reservations and flipping status to `expired`. `404` for another customer's order.

## Payment methods

```
GET /api/order/payment-methods
```

```json
{
  "methods": [
    {
      "id": 1, "name": "card_to_card", "fa_name": "کارت به کارت",
      "channels": [ { "id": 1, "name": "Mellat card-to-card", "fa_name": "...", "account_number": null, "card_number": "6104...", "owner_name": "UzShop" } ]
    },
    { "id": 2, "name": "deposit_to_account", "fa_name": "واریز به حساب", "channels": [ ... ] }
  ]
}
```

`online` and `credit` are also listed (seeded `available=True`) but have **no pay
endpoint** yet.

## Confirm manual payment

```
POST /api/order/<order_id>/pay
{ "payment_method": "card_to_card", "payment_channel_id": 1, "ref_number": "TRX-123", "resource_account_number": "..." }
```

- `payment_method` must be `card_to_card` or `deposit_to_account`; `payment_channel_id`
  must be a channel that **supports** that method (`400` otherwise).
- Creates a `success` `OrderPayment`, sets order status `success`, clears
  `reservation_expires_at`, and links `successful_payment`.
- **Idempotent:** calling again on an already-`success` order returns the current
  order unchanged (no duplicate payment row).
- `400` if the order is not `payment_waiting` (e.g. cancelled or already paid);
  `404` if the order does not belong to the customer.

## Cancel

```
POST /api/order/<order_id>/cancel
```

Releases all stock reservations (normal `reserved` decremented / serialized rows
freed) and sets status `failed`. Allowed only while `payment_waiting`
(`400` otherwise, `404` if not the customer's order).

## Expiry job

`python manage.py expire_orders` expires all stale `payment_waiting` orders and
releases their stock. Detail/list reads also expire lazily, so no background worker
is strictly required. `ORDER_RESERVATION_MINUTES` (default 30) controls the window.

## Order flow (for frontend)

1. Build cart, set address (`PUT /api/cart/address`), run `GET /api/cart/validate`.
2. `POST /api/order/` → order `payment_waiting` with a reservation deadline.
3. `GET /api/order/payment-methods` for the channel to display.
4. After the customer pays manually, `POST /api/order/<id>/pay` with the method
   and channel (`ref_number` + optional `resource_account_number`).
5. Order becomes `success`. Poll `GET /api/order/<id>` for confirmation; handle
   `expired` if the reservation lapsed before payment.