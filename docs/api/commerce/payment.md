# Payments API

Payment configuration and transactions are owned by `domains.payments`.

Payment models and business rules live in this domain. Customer order-payment HTTP
routes remain in the Order domain and call `PaymentService`; payment administration
uses the Payments URL namespace.

## Customer methods

```text
GET /api/order/payment-methods
```

Returns active fixed payment methods and their active, supported channels. Online
channels are returned only when their channel code has an implemented provider in
`domains/payments/online_payment_providers/`.

Fixed method codes are `online`, `card_to_card`, `deposit_to_account`, and `credit`.
Administrators can edit labels and activation state, but not method codes.

## Manual payment

```text
POST /api/order/<order_id>/pay
```

```json
{
  "payment_method": "card_to_card",
  "payment_channel_id": 1,
  "ref_number": "TRX-123",
  "resource_account_number": "..."
}
```

This preserves the existing manual-payment behavior: a valid submission creates a
`successful` payment and changes the order to `paid`. Online and credit execution
are not implemented.

## Administration

All administrative routes require an admin JWT and the corresponding `payments.*`
model permission.

```text
GET   /api/payments/admin/methods
PATCH /api/payments/admin/methods/<id>

GET   /api/payments/admin/channels
POST  /api/payments/admin/channels
GET   /api/payments/admin/channels/<id>
PATCH /api/payments/admin/channels/<id>
POST  /api/payments/admin/channels/<id>/methods
```

Method updates accept `name`, `fa_name`, and `is_active`. Channel codes are
immutable after creation. Channel-method replacement accepts:

```json
{ "payment_method_ids": [1, 2] }
```

Channel list responses mask account and card numbers; detail responses include the
full values for authorized editors. Channels are deactivated rather than deleted.
Logos reference an available image managed by the Files domain.

Assigning `online` requires a provider module matching the immutable channel code.
For example, channel code `saman` requires:

```text
domains/payments/online_payment_providers/saman.py
```

The module must export `SamanProvider`, derived from `BaseOnlinePaymentProvider`.
No online provider implementation is included yet.
