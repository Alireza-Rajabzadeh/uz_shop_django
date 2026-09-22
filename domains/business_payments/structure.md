# Business Payments Domain

Business-scoped payment configuration and payment processing. Every record
in this domain belongs to exactly one `BusinessProfile`. A vendor can only
see and modify data that belongs to their own business.

Built as a direct counterpart of `domains/payments` with business tenancy
added throughout.

---

## Models

```
BusinessPaymentStatus
    name            CharField(50, unique)       # e.g. "pending", "successful", "failed"
    title           CharField(100)              # human-readable, e.g. "پرداخت موفق"
    description     TextField(blank)
    is_active       BooleanField(default=True)
    created_at      DateTimeField(auto_now_add)

BusinessPaymentMethod  ← ImmutableCodeModel
    business        FK → BusinessProfile        (CASCADE)
    code            CharField(50)               # immutable after creation
    name            CharField(100)
    fa_name         CharField(100)
    description     TextField(blank)
    icon_file       FK → File                   (SET_NULL, nullable)
    point_to_channel_field   TextChoices        # card_number | account_number | owner_name
    requires_documents       BooleanField
    is_active       BooleanField
    created_at / updated_at
    UNIQUE(business, code)

BusinessPaymentChannel  ← ImmutableCodeModel
    business        FK → BusinessProfile        (CASCADE)
    code            CharField(100)              # immutable after creation
    name / fa_name
    account_number / card_number / owner_name   # nullable, sensitive
    extra_data      JSONField(nullable)
    is_active       BooleanField
    logo_file       FK → File                   (SET_NULL, nullable)
    created_at / updated_at
    UNIQUE(business, code)

BusinessPaymentChannelSupportedMethod
    payment_channel FK → BusinessPaymentChannel (CASCADE)
    payment_method  FK → BusinessPaymentMethod  (CASCADE)
    UNIQUE(payment_channel, payment_method)
    clean() validates online provider availability

BusinessPayment
    business        FK → BusinessProfile        (CASCADE)
    order           FK → Order                  (CASCADE)
    payment_method  FK → BusinessPaymentMethod  (PROTECT)
    payment_channel FK → BusinessPaymentChannel (SET_NULL, nullable)
    status          FK → BusinessPaymentStatus  (PROTECT)
    amount          DecimalField(15,2)
    ref_number / resource_account_number / extra_data
    created_at / updated_at
    INDEX(business), INDEX(order), INDEX(business, order, status)
    CHECK(amount > 0)
    UNIQUE(business, order) WHERE status = "successful"  # partial unique index

BusinessPaymentDocument
    payment         FK → BusinessPayment        (CASCADE)
    file            FK → File                   (PROTECT)
    created_at
    UNIQUE(payment, file)
```

### Relationships

```
BusinessProfile
  ├── business_payment_methods    (BusinessPaymentMethod)
  ├── business_payment_channels   (BusinessPaymentChannel)
  └── business_payments           (BusinessPayment)

BusinessPaymentMethod
  ├── supported_channels          (BusinessPaymentChannelSupportedMethod → BusinessPaymentChannel)
  └── payments                    (BusinessPayment)

BusinessPaymentChannel
  ├── supported_methods           (BusinessPaymentChannelSupportedMethod → BusinessPaymentMethod)
  └── payments                    (BusinessPayment)

BusinessPayment
  ├── documents                   (BusinessPaymentDocument)
  ├── status → BusinessPaymentStatus
  ├── payment_method → BusinessPaymentMethod
  └── payment_channel → BusinessPaymentChannel

BusinessPaymentStatus
  └── payments                    (BusinessPayment)
```

---

## Online Payment Providers

```
online_payment_providers/
    __init__.py       exports provider_availability, provider_class
    base.py           BaseBusinessPaymentProvider (ABC)
                      - create_payment(*, payment, callback_url)
                      - verify_payment(*, payment, request_data)
    registry.py       provider_class(code)  → attempts import of matching module
                      provider_availability(code) → (bool, reason_or_None)
```

No concrete providers are implemented. The registry returns `False` for any
code without a matching module, which blocks creating online-supported
channels for unimplemented providers.

---

## Services

`BusinessPaymentService` is the single service class. A module-level
`service = BusinessPaymentService()` instance is shared by all views.

### Business scoping

Every public method accepts `business` as the first argument. The service
never trusts caller-provided business IDs — it filters all querysets by
the resolved business object.

`resolve_business(vendor)` looks up `BusinessProfile.objects.filter(vendor=vendor)`.

### Methods

| Method | Purpose |
|---|---|
| `_status(name)` | Lookup BusinessPaymentStatus by name |
| `has_available_channel(business)` | Check if any active method+channel combo is available |
| `method_availability(business, method, channel)` | Check single method/channel availability |
| `file_payload(file)` / `logo_payload` | Build file metadata dict via FileService |
| `customer_methods_payload(business)` | Full customer-facing method list with channels |
| `confirm_manual_payment(business, customer, order_id, ...)` | Customer submits manual payment |
| `review_payment(business, payment_id, *, approve, admin)` | Admin approves/rejects pending payment |
| `list_methods(business, ...)` | Admin queryset: search, filter, order |
| `list_channels(business, ...)` | Admin queryset: search, filter, order |
| `channel_payload(channel, masked)` | Full channel dict, mask sensitive fields |
| `create_channel(business, ...)` | Create channel + supported methods atomically; auto-generates `code` and defaults `name` (from `fa_name`/`code`) when missing |
| `update_channel(business, channel, ...)` | Update channel, replace supported methods |
| `_generate_channel_code(base, business)` | Unique English channel code from slug or random fallback, scoped to business |
| `get_channel(business, channel_id)` | Single channel detail (owner-scoped; 404 otherwise) |
| `delete_channel(business, channel_id)` | Delete channel when owner-scoped and zero payments; cascades supported-method rows |
| `list_payments(business, ...)` | Payment list with search, status filter |
| `get_payment(business, payment_id)` | Single payment detail |
| `payment_payload(payment)` | Payment dict with nested status/method/channel |
| `list_documents(business, payment_id)` | Documents for a payment |
| `document_payload(document)` | Document dict with file URL |
| `validate_logo(logo_file)` | File must be available image |
| `validate_supported_methods(business, code, methods)` | Online provider check |

### Exceptions

- `BusinessPaymentService.ValidationError(errors)` — caught in views, raised as DRF `ValidationError`
- `BusinessPaymentService.NotFoundError` — caught in views, raised as DRF `NotFound`

### Payment flow

```
confirm_manual_payment
  → _expire_stale_order (check reservation)
  → _confirm_manual_payment
      → validate order status, method, channel, linkage, documents
      → create BusinessPayment (status=pending)
      → upload documents via FileService
      → transition order to payment_processing
      → record order history

review_payment
  → lock payment + order (select_for_update)
  → approve: status=successful, order=paid, consume reservations
  → reject:  status=failed, order=payment_failed, release reservations
  → record order history
```

---

## Serializers

| Serializer | Purpose |
|---|---|
| `BaseListQuerySerializer` | Shared list query params: search, is_active, ordering |
| `ListQuerySerializer` | Method list query params: extends base + has_point_to_channel |
| `ChannelListQuerySerializer` | Channel list query params: extends base + supported_method |
| `PaymentListQuerySerializer` | Payment list query params: search, status (validated against DB), ordering |
| `BusinessPaymentMethodReadSerializer` | Read: icon (file_payload), supported_channel_count, provider_available/reason |
| `BusinessPaymentChannelWriteSerializer` | Write: code, name, fa_name, account/card/owner, extra_data, is_active, logo_file, payment_method_ids. `code`/`name` optional on create. `code` and `name` are English-only: Persian input is converted through `core.utils.transliteration.to_english_letters` (PersianG2p). Code immutable on update. |
| `ConfirmPaymentSerializer` | Customer payment: payment_method, channel_id, ref_number, documents (image only, ≤10MB) |

---

## Views

All views extend `BusinessPaymentAPIView`:
- `authentication_classes = [VendorJWTAuthentication]`
- `permission_classes = [IsAuthenticated]`
- `_get_business(request)` resolves the vendor's business via `resolve_business`
- `paginated()` helper for `PageNumberPagination`

| View | Method | URL | Purpose |
|---|---|---|---|
| `VendorBusinessPaymentMethodList` | GET | `methods` | List business payment methods |
| `VendorBusinessPaymentMethodDetail` | GET | `methods/<id>` | Retrieve method (read-only) |
| `VendorBusinessPaymentChannelList` | GET/POST | `channels` | List/create channels (business-scoped) |
| `VendorBusinessPaymentChannelDetail` | GET/PATCH/DELETE | `channels/<id>` | Retrieve/update/delete channel (owner-scoped) |
| `VendorBusinessPaymentChannelMethods` | POST | `channels/<id>/methods` | Replace supported methods |
| `VendorBusinessPaymentList` | GET | `payments` | List payments |
| `VendorBusinessPaymentDetail` | GET | `payments/<id>` | Retrieve payment |
| `VendorBusinessPaymentDocumentList` | GET | `payments/<id>/documents` | List payment documents |

All endpoints operate within the authenticated vendor's business scope.

---

## URLs

Mounted in `config/urls.py` at:
```
api/vendor/business-payments/ → domains.business_payments.urls
```

---

## Admin

| Model | Admin | Notes |
|---|---|---|
| `BusinessPaymentStatus` | `BusinessPaymentStatusAdmin` | list: name, title, is_active |
| `BusinessPaymentMethod` | `BusinessPaymentMethodAdmin` | code readonly; list by business |
| `BusinessPaymentChannel` | `BusinessPaymentChannelAdmin` | code readonly on change; timestamps readonly |
| `BusinessPaymentChannelSupportedMethod` | `BusinessPaymentChannelSupportedMethodAdmin` | junction table |
| `BusinessPayment` | `BusinessPaymentAdmin` | fully read-only; no add/delete |
| `BusinessPaymentDocument` | `BusinessPaymentDocumentAdmin` | fully read-only |

---

## Enums

`domains/business_payments/enums/BusinessPaymentStatusEnum.py`:
```python
class BusinessPaymentStatusEnum(Enum):
    PENDING = 1
    SUCCESSFUL = 2
    FAILED = 3
```

---

## Seeders

`core/management/seeders/business_payment_statuses.py`:
- Seeds `pending`, `successful`, `failed` with Persian titles
- Registered in `core/management/commands/seed.py`

---

## Migrations

| Migration | Purpose |
|---|---|
| `0001_initial` | Creates all original tables, constraints, indexes |
| `0002_businesspaymentstatus_and_more` | Creates `BusinessPaymentStatus` table, converts `status` from CharField to FK, adds composite index |
| `0003_seed_statuses_and_add_unique_index` | Seeds status rows, creates partial unique index for one-successful-payment-per-order |
| `0004_remove_businesspaymentchannel_bpc_business_code_unique_and_more` | Removed channel `business` FK (global channels), unique on `code` alone |
| `0005_remove_method_business_created_updated` | Removed method `business` FK and timestamps |
| `0006_businesspaymentmethod_description` | Adds method `description` |
| `0007_restore_channel_business` | Re-adds channel `business` FK, restores `UNIQUE(business, code)`, backfills existing rows |

---

## Tests

`tests.py` contains two test classes:

**`BusinessPaymentModelTests`** (9 tests):
- Code immutability (method + channel)
- Unique constraint per business (method + channel)
- Code can differ across businesses
- Payment amount must be positive
- One successful payment per order per business
- Online support requires provider
- Document unique per payment

**`BusinessPaymentVendorAPITests`** (25 tests):
- Business isolation: each vendor sees only own methods, channels, payments, documents
- Cross-business channel access returns 404
- Channel list masks card numbers, detail shows full
- Channel create/update with method replacement
- Method update rejects code change
- Channel delete: owner + zero payments succeeds (cascades support rows); cross-business 404; with payments 400
- Method delete returns 405
- Unauthenticated requests return 401
- Vendor without business returns 404

`test_migrations.py` (1 test):
- Verifies all expected tables exist after migration
