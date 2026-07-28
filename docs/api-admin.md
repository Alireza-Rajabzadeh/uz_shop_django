# Admin Panel API Documentation

Base URL: `/api`

Response envelope for all endpoints:

```json
{
  "success": true | false,
  "message": "",
  "data": null | object | array,
  "errors": null | object
}
```

---

## Authentication

### Login

```
POST /users/login
Content-Type: application/json

{
  "username": "admin",
  "password": "secret"
}
```

**Response:**

```json
{
  "success": true,
  "data": {
    "access": "eyJhbGciOiJIUzI1NiIs...",
    "refresh": "eyJhbGciOiJIUzI1NiIs...",
    "user": {
      "id": 1,
      "username": "admin",
      "email": "admin@example.com",
      "permissions": [
        "catalog.view_category",
        "catalog.add_category",
        "catalog.change_category",
        "catalog.delete_category",
        "catalog.assign_details_to_category",
        "catalog.view_categorydetail",
        "catalog.add_categorydetail",
        "catalog.view_product",
        "catalog.add_product",
        "catalog.change_product",
        "catalog.delete_product",
        "catalog.add_detail_to_product",
        "catalog.add_variant_to_product",
        "catalog.view_productvariants",
        "catalog.change_productvariants",
        "catalog.delete_productvariants",
        "catalog.view_productdetails"
      ]
    }
  }
}
```

All subsequent requests must include:

```
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
```

---

### Permissions

```
GET /users/permissions
Authorization: Bearer <token>
```

Returns all system permissions grouped by app + current user's permissions.

**Response:**

```json
{
  "success": true,
  "data": {
    "permissions": {
      "catalog": [
        { "id": 1, "codename": "view_category", "name": "Can view category" },
        { "id": 2, "codename": "add_category", "name": "Can add category" },
        { "id": 3, "codename": "change_category", "name": "Can change category" },
        { "id": 4, "codename": "delete_category", "name": "Can delete category" },
        { "id": 5, "codename": "assign_details_to_category", "name": "Can assign details to category" },
        { "id": 6, "codename": "view_categorydetail", "name": "Can view category detail" },
        { "id": 7, "codename": "add_categorydetail", "name": "Can add category detail" },
        { "id": 8, "codename": "change_categorydetail", "name": "Can change category detail" },
        { "id": 9, "codename": "delete_categorydetail", "name": "Can delete category detail" },
        { "id": 10, "codename": "view_product", "name": "Can view product" },
        { "id": 11, "codename": "add_product", "name": "Can add product" },
        { "id": 12, "codename": "change_product", "name": "Can change product" },
        { "id": 13, "codename": "delete_product", "name": "Can delete product" },
        { "id": 14, "codename": "add_detail_to_product", "name": "Can add product details" },
        { "id": 15, "codename": "add_variant_to_product", "name": "Can add product variants" },
        { "id": 16, "codename": "view_productdetails", "name": "Can view product details" },
        { "id": 17, "codename": "view_productvariants", "name": "Can view product variants" },
        { "id": 18, "codename": "add_productvariants", "name": "Can add product variants (standard)" },
        { "id": 19, "codename": "change_productvariants", "name": "Can change product variants" },
        { "id": 20, "codename": "delete_productvariants", "name": "Can delete product variants" }
      ],
      "auth": [ ... ],
      "customer": [ ... ],
      "location": [ ... ],
      "inventory": [ ... ]
    },
    "user_permissions": [
      "catalog.view_category",
      "catalog.add_category",
      "catalog.assign_details_to_category"
    ]
  }
}
```

Use `user_permissions` to determine which UI actions to show/hide for the logged-in admin.

---

## Categories

### List Categories

```
GET /catalog/categories?name=keyword&status_id=1
Authorization: Bearer <token>
```

**Required permission:** `catalog.view_category`

| Query param | Type | Description |
|---|---|---|
| `name` | string | Partial match filter |
| `status_id` | int | Filter by status ID |

**Response:**

```json
{
  "success": true,
  "data": [
    {
      "id": 1,
      "name": "Clothing",
      "parent": null,
      "parent_name": null,
      "status": 1,
      "status_name": "active",
      "logo": null
    }
  ]
}
```

---

### Get Category Tree

```
GET /catalog/categories/tree
Authorization: Bearer <token>
```

**Required permission:** `catalog.view_category`

Returns categories as nested tree:

```json
{
  "success": true,
  "data": [
    {
      "id": 1,
      "name": "Clothing",
      "status": 1,
      "parent": null,
      "logo": null,
      "children": [
        {
          "id": 2,
          "name": "Men",
          "parent": 1,
          "status": 1,
          "logo": null,
          "children": [
            {
              "id": 3,
              "name": "T-Shirts",
              "parent": 2,
              "status": 1,
              "logo": null,
              "children": []
            }
          ]
        }
      ]
    }
  ]
}
```

---

### Get Single Category

```
GET /catalog/categories/{id}
Authorization: Bearer <token>
```

**Required permission:** `catalog.view_category`

**Response:** Full category object with nested `children`.

---

### Create Category

```
POST /catalog/categories
Content-Type: application/json
Authorization: Bearer <token>
```

**Required permission:** `catalog.add_category`

**Request:**

```json
{
  "name": "Electronics",
  "parent": null,
  "status": 1,
  "logo": null
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `name` | string | yes | |
| `parent` | int \| null | no | Parent category ID |
| `status` | int | no | Default: 1 (active) |
| `logo` | string | no | URL or path |

---

### Update Category

```
PATCH /catalog/categories/{id}
Content-Type: application/json
Authorization: Bearer <token>
```

**Required permission:** `catalog.change_category`

Same body as create. Partial updates supported.

---

### Delete Category

```
DELETE /catalog/categories/{id}
Authorization: Bearer <token>
```

**Required permission:** `catalog.delete_category`

---

### Assign Details to Category

```
POST /catalog/categories/{id}/assign-details
Content-Type: application/json
Authorization: Bearer <token>
```

**Required permission:** `catalog.assign_details_to_category`

This is a **sync** operation. Pass the full list of detail assignments — any existing assignments not in the request will be removed.

**Request:**

```json
{
  "details": [
    { "detail_id": 1, "value": "default color value" },
    { "detail_id": 2, "value": "default size value" }
  ]
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `detail_id` | int | yes | ID of CategoryDetail |
| `value` | string | no | Default value for this attribute |

**Behavior:**
- Adds new detail–category links from the request
- Removes existing links not present in the request
- Keeps links that already exist (doesn't duplicate)

---

## Category Details (Descriptive Fields)

These definitions store descriptive product data. Sellable choices such as color and
storage use variant attributes and options instead.

### List Category Details

```
GET /catalog/category-details?name=keyword&type=select
Authorization: Bearer <token>
```

**Required permission:** `catalog.view_categorydetail`

| Query param | Type | Description |
|---|---|---|
| `name` | string | Partial match |
| `type` | string | Filter by type: `text`, `number`, `select` |

**Response:**

```json
{
  "success": true,
  "data": [
    {
      "id": 1,
      "name": "color",
      "type": "select",
      "required": true,
      "options": "red,blue,green,black,white",
      "filterable": true
    }
  ]
}
```

---

### Create Category Detail

```
POST /catalog/category-details
Content-Type: application/json
Authorization: Bearer <token>
```

**Required permission:** `catalog.add_categorydetail`

**Request:**

```json
{
  "name": "material",
  "type": "select",
  "required": false,
  "options": "cotton,polyester,wool,leather",
  "filterable": true
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `name` | string | yes | Must be unique |
| `type` | string | yes | One of: `text`, `number`, `select` |
| `required` | bool | no | Default: false |
| `options` | string | no | Comma-separated for `select` type |
| `filterable` | bool | no | Default: true |

---

### Get / Update / Delete Category Detail

```
GET    /catalog/category-details/{id}
PATCH  /catalog/category-details/{id}
DELETE /catalog/category-details/{id}
Authorization: Bearer <token>
```

**Required permissions:** `view`, `change`, `delete_categorydetail` respectively.

---

## Products

### List Products

```
GET /catalog/products?name=keyword&category_id=1&status_id=1
Authorization: Bearer <token>
```

**Required permission:** `catalog.view_product`

| Query param | Type | Description |
|---|---|---|
| `name` | string | Partial match |
| `category_id` | int | Filter by category |
| `status_id` | int | Filter by status |

**Response:**

```json
{
  "success": true,
  "data": [
    {
      "id": 1,
      "name": "Cotton T-Shirt",
      "category": 3,
      "category_name": "T-Shirts",
      "status": 1,
      "status_name": "active",
      "description": "A comfortable cotton t-shirt",
      "variant_count": 4
    }
  ]
}
```

---

### Get Single Product

```
GET /catalog/products/{id}
Authorization: Bearer <token>
```

**Required permission:** `catalog.view_product`

Returns full product with nested `details` and `variants`:

```json
{
  "success": true,
  "data": {
    "id": 1,
    "name": "Cotton T-Shirt",
    "status": 1,
    "category": 3,
    "description": "A comfortable cotton t-shirt",
    "details": [
      {
        "id": 1,
        "product": 1,
        "detail": 1,
        "detail_name": "color",
        "detail_type": "select",
        "value": "red",
        "extra_value": null
      }
    ],
    "variants": [
      {
        "id": 1,
        "product": 1,
        "sku": "TSH-RED-L",
        "price": "29.99",
        "discount_type": null,
        "discount_value": null,
        "inventory_strategy": 1,
        "inventory_strategy_code": "normal",
        "inventory_strategy_name": "Normal",
        "details": []
      }
    ]
  }
}
```

---

### Create Product

```
POST /catalog/products
Content-Type: application/json
Authorization: Bearer <token>
```

**Required permission:** `catalog.add_product`

```json
{
  "name": "Cotton T-Shirt",
  "category": 3,
  "description": "A comfortable cotton t-shirt"
}
```

Status defaults to `pending`. After creating the product, add details via `POST /products/{id}/details` and variants via `POST /products/{id}/variants`.

---

### Create Complete Product

```
POST /catalog/products/create
Content-Type: application/json
Authorization: Bearer <token>
```

Creates the product and its selected category-detail values atomically. Status is assigned to `pending` by the server.

```json
{
  "name": "Cotton T-Shirt",
  "category_ids": [3],
  "description": "A comfortable cotton t-shirt",
  "details": [{ "detail_id": 1, "value": "Cotton" }]
}
```

Each submitted detail must be assigned to the selected category. Required, number, and select definitions are validated before the product is saved.

---

### Update Complete Product

```
GET   /catalog/products/{id}/update
PATCH /catalog/products/{id}/update
Content-Type: application/json
Authorization: Bearer <token>
```

**Required permission:** `catalog.change_product`

GET returns the complete product for the edit form. PATCH accepts the same aggregate body as complete creation, preserves status, and atomically replaces category-derived product details.

---

### Update Product

```
PATCH /catalog/products/{id}
Content-Type: application/json
Authorization: Bearer <token>
```

**Required permission:** `catalog.change_product`

Partial update of `name` and `description` only. Omitted details are preserved. Use the complete-update endpoint to change category or replace category-derived details atomically.

---

### Delete Product

```
DELETE /catalog/products/{id}
Authorization: Bearer <token>
```

**Required permission:** `catalog.delete_product`

---

## Product Details (EAV Attribute Values)

### List Product Details

```
GET /catalog/products/{product_id}/details
Authorization: Bearer <token>
```

**Required permission:** `catalog.view_productdetails`

Return all attribute values assigned to a product.

---

### Add Details to Product

```
POST /catalog/products/{product_id}/details
Content-Type: application/json
Authorization: Bearer <token>
```

**Required permission:** `catalog.add_detail_to_product`

Accepts a single object or an array:

```json
// Single
{ "detail_id": 1, "value": "red", "extra_value": null }

// Bulk
[
  { "detail_id": 1, "value": "red" },
  { "detail_id": 2, "value": "XL" }
]
```

Upserts — if a detail already exists for this product, its value is updated.

---

## Variant Attributes and Options

Variant attributes are global axes such as `Color` and `Storage`. Options belong to
one attribute and are shared globally.

```
GET|POST          /catalog/variant-attributes
GET|PATCH|DELETE  /catalog/variant-attributes/{id}
GET|POST          /catalog/variant-options?search=black&attribute_id=1
GET|PATCH|DELETE  /catalog/variant-options/{id}
```

Attribute write: `{ "name": "Color" }`

Option write:

```json
{ "attribute": 1, "name": "Black", "sku_code": "BLK" }
```

`sku_code` is normalized to uppercase, accepts only ASCII letters and numbers,
has a maximum length of 16, and is globally unique case-insensitively. Attribute
names are normalized and globally unique; option names are normalized and unique
within their attribute. Lists are plain arrays and accept `search`.

Category suggestions are a full-replacement assignment and do not restrict which
attributes a product variant may use:

```
GET|POST /catalog/categories/{id}/assign-variant-attributes
```

```json
{ "attributes": [1, 2] }
```

Both methods require `catalog.assign_variant_attributes_to_category`. GET returns
`assignments` plus all `attributes` with an `assigned` flag, with assigned rows first.

---

## Product Variants

### Variant Form Options

```
GET /catalog/products/{product_id}/variant-form-options
Authorization: Bearer <token>
```

**Required permission:** `catalog.view_productvariants`, `catalog.add_variant_to_product`, or `catalog.change_productvariants`

Returns product/category context, `inventory_strategies` containing both `normal`
and `serialized`, `default_warehouse`, and all global attributes with nested
options. The endpoint returns a setup validation error unless exactly one default
warehouse exists. Category suggestions have `category_default: true`.
An optional `search` query matches attribute names, option names, and option codes.

---

### List Variants for a Product

```
GET /catalog/products/{product_id}/variants
Authorization: Bearer <token>
```

**Required permission:** `catalog.view_productvariants`

---

### Add Variant to Product

```
POST /catalog/products/{product_id}/variants
Content-Type: application/json
Authorization: Bearer <token>
```

**Required permission:** `catalog.add_variant_to_product`

```json
{
  "price": "29.99",
  "discount_type": null,
  "discount_value": null,
  "inventory_strategy_code": "normal",
  "inventory": { "quantity": 10, "sellable": 8 },
  "selections": [
    { "attribute_id": 1, "option_id": 10 },
    { "attribute_id": 2, "option_id": 21 }
  ]
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `price` | decimal | yes | |
| `discount_type` | string | no | `percentage` or `fixed` |
| `discount_value` | decimal | no | |
| `inventory_strategy_code` | string | yes | `normal` or `serialized` |
| `inventory` | object | for normal | Full default-warehouse snapshot: `quantity`, `sellable` |
| `serial_items` | array | for serialized | Full serialized snapshot: `id?`, `serial_number`, `on_sale` |
| `selections` | array | yes | At least one unique attribute/option pair |

The option must belong to the submitted attribute. Category suggestions are not
restrictions. The backend rejects duplicate combinations within one product and
generates a globally unique read-only SKU using attribute-ID order:
`CG{category_id}-PD{product_id}-{option_codes}`, for example
`CG12-PD120-BLK-128GB`. Selection edits, option code edits, and complete product
category changes regenerate affected SKUs. Initial inventory is written atomically
with the variant. A serialized create uses this inventory shape instead:

```json
{
  "inventory_strategy_code": "serialized",
  "serial_items": [
    { "serial_number": "IMEI 001", "on_sale": true },
    { "serial_number": "IMEI 002", "on_sale": false }
  ]
}
```

Normal stock uses the single default warehouse and preserves the existing
`reserved` value on update. It enforces
`0 <= reserved <= sellable <= quantity`; availability is `sellable - reserved`.
Serialized quantity is the number of serial rows. New rows use `in_stock`, the
default warehouse, and `reserved: false`. Serial numbers have collapsed whitespace
and are globally unique ignoring case.

Variant reads expose:

```json
{
  "sku": "CG12-PD120-BLK-128GB",
  "total_item_count": 10,
  "sellable_item_count": 8,
  "available_item_count": 6,
  "selections": [
    {
      "attribute_id": 1,
      "attribute_name": "Color",
      "option_id": 10,
      "option_name": "Black",
      "sku_code": "BLK"
    }
  ]
}
```

Variant list/read responses expose only these three inventory counts, never full
serial rows. For serialized variants, `sellable_item_count` counts all rows with
`on_sale: true`; `available_item_count` counts rows whose status code is
`in_stock`, whose `on_sale` is true, and which are not reserved. Warehouse status
is not part of this rule because warehouse statuses do not currently have a stable
code.

---

## Variants (Standalone CRUD)

### List All Variants

```
GET /catalog/variants?product_id=1&sku=keyword
Authorization: Bearer <token>
```

**Required permission:** `catalog.view_productvariants`

---

### Get / Update / Delete Variant

```
GET    /catalog/variants/{id}
PATCH  /catalog/variants/{id}
DELETE /catalog/variants/{id}
Authorization: Bearer <token>
```

**Required permissions:** `view`, `change`, `delete_productvariants`.

PATCH may include normal `inventory` or serialized `serial_items`. `serial_items`
is an atomic full snapshot: omit `id` to create, include `id` to update/retain, and
omit an existing editable row to delete it. Sold, reserved, or non-`in_stock` rows
must remain present and unchanged. A strategy change requires the current strategy
to have no stock; empty normal stock rows are cleaned up automatically. Submit the
complete target-strategy snapshot with the change. Variant deletion is rejected
for nonzero normal stock or any serialized rows.

---

## Variant Inventory Edit Detail

```
GET /inventory/variants/{variant_id}
Authorization: Bearer <token>
```

**Required permission:** `catalog.view_productvariants`

Returns `strategy`, the three summary counts, and exactly one populated detail
field. Normal variants return:

```json
{
  "variant_id": 42,
  "strategy": { "id": 1, "code": "normal", "name": "Normal" },
  "total_item_count": 10,
  "sellable_item_count": 8,
  "available_item_count": 6,
  "inventory": {
    "warehouse": { "id": 1, "code": "WH-00001", "name": "Main", "status": "available" },
    "quantity": 10,
    "sellable": 8,
    "reserved": 2,
    "available": 6
  },
  "serial_items": null
}
```

Serialized variants return `inventory: null` and `serial_items` rows with `id`,
`serial_number`, `on_sale`, `reserved`, `status: {code, name}`, `warehouse`, and
`editable`.

---

## Permission Reference

### Catalog

| Codename | Endpoint / Action |
|---|---|
| `catalog.view_category` | GET categories, categories/tree, categories/{id} |
| `catalog.add_category` | POST categories |
| `catalog.change_category` | PATCH categories/{id} |
| `catalog.delete_category` | DELETE categories/{id} |
| `catalog.assign_details_to_category` | POST categories/{id}/assign-details |
| `catalog.assign_variant_attributes_to_category` | GET/POST categories/{id}/assign-variant-attributes |
| `catalog.view_variantattribute` / `add_...` / `change_...` / `delete_...` | Variant attribute CRUD |
| `catalog.view_variantoption` / `add_...` / `change_...` / `delete_...` | Variant option CRUD |
| `catalog.view_categorydetail` | GET category-details, category-details/{id} |
| `catalog.add_categorydetail` | POST category-details |
| `catalog.change_categorydetail` | PATCH category-details/{id} |
| `catalog.delete_categorydetail` | DELETE category-details/{id} |
| `catalog.view_product` | GET products, products/{id} |
| `catalog.add_product` | POST products |
| `catalog.change_product` | PATCH products/{id}, GET/PATCH products/{id}/update |
| `catalog.delete_product` | DELETE products/{id} |
| `catalog.view_productdetails` | GET products/{id}/details |
| `catalog.add_detail_to_product` | POST products/{id}/details |
| `catalog.view_productvariants` | GET products/{id}/variants, GET products/{id}/variant-form-options, GET variants, GET variants/{id}, GET inventory/variants/{id} |
| `catalog.add_variant_to_product` | POST products/{id}/variants, GET products/{id}/variant-form-options |
| `catalog.change_productvariants` | PATCH variants/{id}, GET products/{id}/variant-form-options |
| `catalog.delete_productvariants` | DELETE variants/{id} |

---

## Error Responses

### 401 Unauthenticated

```json
{
  "success": false,
  "message": "",
  "data": null,
  "errors": {
    "detail": "Authentication credentials were not provided."
  }
}
```

### 403 Permission Denied

```json
{
  "success": false,
  "message": "",
  "data": null,
  "errors": {
    "detail": "You do not have permission to perform this action."
  }
}
```

### 400 Validation Error

```json
{
  "success": false,
  "message": "",
  "data": null,
  "errors": {
    "name": ["This field is required."],
    "type": ["\"invalid\" is not a valid choice."]
  }
}
```

### 404 Not Found

```json
{
  "success": false,
  "message": "",
  "data": null,
  "errors": {
    "detail": "Not found."
  }
}
```
