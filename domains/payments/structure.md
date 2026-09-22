# Current Payments Domain Structure

## Directory

```
domains/payments/
├── __init__.py
├── admin.py
├── apps.py
├── models.py
├── serializers.py
├── services.py
├── tests.py
├── test_migrations.py
├── urls.py
├── views.py
├── online_payment_providers/
│   ├── __init__.py
│   ├── base.py
│   └── registry.py
└── migrations/
    ├── __init__.py
    ├── 0001_adopt_order_payment_tables.py
    ├── 0002_refactor_payment_models.py
    ├── 0003_paymentmethod_icon_path.py
    └── 0004_paymentmethod_configuration_and_documents.py
```

## Models

### ImmutableCodeModel (abstract)
Prevents changing `code` field after creation.

### PaymentMethod (`shop_order_payment_method`)
| Field | Type | Notes |
|---|---|---|
| code | CharField(50, unique) | Immutable |
| name | CharField(100) | |
| fa_name | CharField(100) | |
| icon_file | FK → files.File | SET_NULL, null |
| point_to_channel_field | CharField(32) | choices: card_number, account_number, owner_name |
| requires_documents | BooleanField | default=False |
| is_active | BooleanField | default=True |

### PaymentChannel (`shop_order_payment_channel`)
| Field | Type | Notes |
|---|---|---|
| code | CharField(100, unique) | Immutable |
| name | CharField(100) | |
| fa_name | CharField(100) | blank |
| account_number | CharField(50) | null, blank |
| card_number | CharField(30) | null, blank |
| owner_name | CharField(150) | null, blank |
| extra_data | JSONField | null, blank |
| is_active | BooleanField | default=True |
| logo_file | FK → files.File | SET_NULL, null |
| created_at | DateTimeField | auto_now_add |
| updated_at | DateTimeField | auto_now |

### PaymentChannelSupportedMethod (`shop_order_payment_channel_support`)
| Field | Type | Notes |
|---|---|---|
| payment_channel | FK → PaymentChannel | CASCADE |
| payment_method | FK → PaymentMethod | CASCADE |

Constraints: UniqueConstraint(payment_channel, payment_method)
Validation: online provider availability checked on save

### Payment (`shop_order_payment`)
| Field | Type | Notes |
|---|---|---|
| order | FK → order.Order | CASCADE, related_name="payments" |
| payment_method | FK → PaymentMethod | PROTECT |
| payment_channel | FK → PaymentChannel | SET_NULL, null |
| amount | DecimalField(15,2) | |
| status | CharField(16) | choices: pending, successful, failed |
| ref_number | CharField(128) | null, blank |
| resource_account_number | CharField(64) | null, blank |
| extra_data | JSONField | null, blank |
| created_at | DateTimeField | auto_now_add |
| updated_at | DateTimeField | auto_now |

Constraints:
- `shop_payment_amount_positive`: amount > 0
- `shop_payment_status_valid`: status in [pending, successful, failed]
- `shop_payment_one_successful_order`: one successful payment per order

### PaymentDocument (`shop_payment_document`)
| Field | Type | Notes |
|---|---|---|
| payment | FK → Payment | CASCADE, related_name="documents" |
| file | FK → files.File | PROTECT |
| created_at | DateTimeField | auto_now_add |

Constraints: UniqueConstraint(payment, file)

## Online Payment Providers

### base.py
```python
class BaseOnlinePaymentProvider(ABC):
    def create_payment(self, *, payment, callback_url):
        """Create a provider-side payment and return redirect information."""
    def verify_payment(self, *, payment, request_data):
        """Verify a provider callback and return provider verification data."""
```

### registry.py
- `provider_class(code)` — dynamically imports `domains.payments.online_payment_providers.<code>`, looks for `<Code>Provider` class
- `provider_availability(code)` — returns `(True, None)` if provider exists, `(False, "Online payment provider is not implemented.")` if not

**No concrete providers implemented.**

## Services

### PaymentService

**Exceptions:**
- `ValidationError(errors)`
- `NotFoundError(message)`

**Constants:**
- `MANUAL_METHODS = ("card_to_card", "deposit_to_account")`

**Static methods:**
- `has_available_channel()` → bool
- `method_availability(method, channel=None)` → (bool, reason)
- `file_payload(file)` → dict | None
- `logo_payload` — alias for file_payload
- `_mask(value)` → str
- `validate_logo(logo_file)`
- `validate_method_icon(icon_file)`
- `validate_supported_methods(channel_code, methods)`
- `_record_payment_history(order, action_code, description, user=None)`
- `_consume_order_reservations(order)`
- `_release_order_reservations(order)`

**Instance methods:**
- `customer_methods_payload()` → list[dict]
- `confirm_manual_payment(customer, order_id, **kwargs)` → order
- `_expire_stale_order(customer, order_id)` → bool [@atomic]
- `_confirm_manual_payment(customer, order_id, **kwargs)` → order [@atomic]
- `review_payment(payment_id, *, approve, admin)` → order [@atomic]
- `list_methods(*, search, is_active, ordering)` → queryset
- `list_channels(*, search, is_active, supported_method, ordering)` → queryset
- `channel_payload(channel, *, masked)` → dict
- `create_channel(*, supported_methods, **values)` → channel [@atomic]
- `update_channel(channel, *, supported_methods, **values)` → channel [@atomic]
- `get_channel(channel_id)` → channel

## Views (all require AdminJWTAuthentication)

| View | Methods | URL | Description |
|---|---|---|---|
| AdminPaymentMethodList | GET | admin/methods | List methods with filters |
| AdminPaymentMethodDetail | PATCH | admin/methods/\<method_id\> | Partial update (code immutable) |
| AdminPaymentReview | POST | admin/payments/\<payment_id\>/\<decision\> | approve or reject |
| AdminPaymentChannelList | GET, POST | admin/channels | List (masked) / Create |
| AdminPaymentChannelDetail | GET, PATCH | admin/channels/\<channel_id\> | Full detail / Partial update |
| AdminPaymentChannelMethods | POST | admin/channels/\<channel_id\>/methods | Replace supported methods |

Customer-facing payment views live in `order/views.py`:
| View | Methods | URL | Description |
|---|---|---|---|
| OrderPaymentMethodsView | GET | /api/order/payment-methods | List customer payment methods |
| OrderConfirmPaymentView | POST | /api/order/\<order_id\>/pay | Submit manual payment |

## Serializers

| Serializer | Usage |
|---|---|
| ConfirmPaymentSerializer | Customer manual payment submission |
| ListQuerySerializer | Admin method list query params |
| ChannelListQuerySerializer | Admin channel list query params |
| PaymentMethodReadSerializer | Admin method read (with provider_available) |
| PaymentMethodUpdateSerializer | Admin method update (code immutable) |
| PaymentChannelWriteSerializer | Admin channel create/update |

## Seed Data

| ID | Code | Name | fa_name |
|---|---|---|---|
| 1 | online | Online payment | پرداخت آنلاین |
| 2 | card_to_card | Card to card | کارت به کارت |
| 3 | deposit_to_account | Deposit to account | واریز به حساب |
| 4 | credit | Credit | اعتبار |

## Cross-Domain Dependencies

**Payments depends on:**
- `domains.files` — File, FileService
- `domains.order` — Order, OrderStatus, OrderAction, OrderHistory

**Order uses payments:**
- `order/views.py` — ConfirmPaymentSerializer, PaymentService
- `order/services.py` — PaymentService.has_available_channel()
- `order/models/order.py` — Order.successful_payment (OneToOneField)

## What Is Implemented vs Missing

### Implemented
- PaymentMethod CRUD (admin list + update)
- PaymentChannel CRUD (admin list + create + update + detail)
- PaymentChannelSupportedMethod management
- Manual payment submission (customer)
- Manual payment review (admin approve/reject)
- Customer payment methods listing
- Online provider registry (abstract base + dynamic loader)
- Payment documents upload
- Card/account masking
- Order status transitions (payment_pending → payment_processing → paid/failed)
- Order history recording for payment actions

### Missing
- No concrete online payment providers
- No online payment initiation flow
- No payment callback/verification endpoint
- No customer payment status endpoint
- No customer payment history
- No refund mechanism
- No vendor/business payment dashboard
- No Refund model
- No "refunded" order status
- No provider_data/provider_authority on Payment model
