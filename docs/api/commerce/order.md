# Order & Payment API

Base URL: `/api/order`. All endpoints require a **customer JWT**; admin/staff tokens
are rejected.

Order lifecycle:

```
payment_pending --(manual payment confirmed)--> paid
       │
       ├--(customer cancel)--------------------> cancelled
       └--(reservation expired)----------------> payment_expired
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

`201` returns the full order payload (starts in `payment_pending`).

`400` `{ "address": [...] }` if no address, `{ "cart": [...] }` if empty,
`{ "items": [...] }` listing each problematic SKU otherwise.

## Order payload

```json
{
  "id": 1,
  "status": {
    "id": 110,
    "name": "payment_pending",
    "fa_name": "در انتظار پرداخت"
  },
  "available_actions": [
    {
      "id": 1,
      "code": "cancel",
      "name": "Cancel order",
      "fa_name": "لغو سفارش"
    }
  ],
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
`payment_pending` orders whose `reservation_expires_at` has passed, releasing their
stock reservations and flipping status to `payment_expired`. `404` for another customer's order.

## Payments

Payment models and business rules are owned by the Payments domain. Order owns the
customer-facing order payment routes and delegates to `PaymentService`. See
[`payment.md`](payment.md) for the customer and administrative contracts.

## Confirm manual payment

```
POST /api/order/<order_id>/pay
{ "payment_method": "card_to_card", "payment_channel_id": 1, "ref_number": "TRX-123", "resource_account_number": "..." }
```

- `payment_method` must be `card_to_card` or `deposit_to_account`; `payment_channel_id`
  must be a channel that **supports** that method (`400` otherwise).
- Creates a `successful` payment, sets order status `paid`, clears
  `reservation_expires_at`, and links `successful_payment`.
- **Idempotent:** calling again on an already-`paid` order returns the current
  order unchanged (no duplicate payment row).
- `400` if the order is not `payment_pending` (e.g. cancelled or already paid);
  `404` if the order does not belong to the customer.

## Cancel

```
POST /api/order/<order_id>/cancel
```

Releases all stock reservations (normal `reserved` decremented / serialized rows
freed) and sets status `cancelled`. Allowed only while `payment_pending`
(`400` otherwise, `404` if not the customer's order).

## Actions

Available actions are embedded in customer and admin order responses. They are assigned
to the order's current status in `order_status_actions` and filtered by the action's
customer/admin actor flags. Each embedded action contains `id`, `code`, `name`, and
`fa_name`; clients use `code` as the stable execution identifier.

```
GET  /api/order/<order_id>/actions
POST /api/order/<order_id>/actions/<action_code>
GET  /api/order/admin/orders/<order_id>/actions
POST /api/order/admin/orders/<order_id>/actions/<action_code>
```

Customer routes require ownership. Admin discovery requires `order.view_order`; admin
execution requires `order.change_order`. Executing `cancel` also releases inventory
reservations and clears `reservation_expires_at`. The dedicated customer cancel route
remains available and delegates to the same action workflow.

Every action that changes an order creates an `order_history` audit row in the same
database transaction. The row stores the action, only the order fields whose values
changed, an actor-aware description, and its creation time. Admin order detail responses
include these entries under `history`, newest first:

```json
{
  "history": [
    {
      "id": 10,
      "action": {
        "id": 1,
        "code": "cancel",
        "name": "Cancel order",
        "fa_name": "لغو سفارش"
      },
      "before_values": {
        "status_id": 110,
        "reservation_expires_at": "2026-08-13T12:00:00+00:00"
      },
      "after_values": {
        "status_id": 500,
        "reservation_expires_at": null
      },
      "description": "Order action 'Cancel order' executed by customer.",
      "created_at": "2026-08-13T11:30:00+00:00"
    }
  ]
}
```

## Expiry job

`python manage.py expire_orders` expires all stale `payment_pending` orders and
releases their stock. Detail/list reads also expire lazily, so no background worker
is strictly required. `ORDER_RESERVATION_MINUTES` (default 30) controls the window.

## Order flow (for frontend)

1. Build cart, set address (`PUT /api/cart/address`), run `GET /api/cart/validate`.
2. `POST /api/order/` → order `payment_pending` with a reservation deadline.
3. `GET /api/order/payment-methods` for the channel to display.
4. After the customer pays manually, `POST /api/order/<id>/pay` with the method
   and channel (`ref_number` + optional `resource_account_number`).
5. Order becomes `paid`. Poll `GET /api/order/<id>` for confirmation; handle
   `payment_expired` if the reservation lapsed before payment.
