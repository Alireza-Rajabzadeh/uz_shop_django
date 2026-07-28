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

## Category Details (Attributes)

These are the **attribute definitions** (e.g., "color", "size", "material").

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

## Product Variants

### Variant Form Options

```
GET /catalog/products/{product_id}/variant-form-options
Authorization: Bearer <token>
```

**Required permission:** `catalog.view_productvariants`, `catalog.add_variant_to_product`, or `catalog.change_productvariants`

Returns product context, the current normal creation strategy, and all detail definitions. Category-assigned details have `category_default: true` so clients can prioritize them without restricting selection.

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
  "sku": "TSH-RED-L",
  "price": "29.99",
  "discount_type": null,
  "discount_value": null,
  "details": [
    { "detail_id": 1, "value": "Red" },
    { "detail_id": 2, "value": "Large" }
  ]
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `sku` | string | no | Stock keeping unit |
| `price` | decimal | yes | |
| `discount_type` | string | no | `percentage` or `fixed` |
| `discount_value` | decimal | no | |
| `details` | array | no | Selected detail/value pairs; details need not belong to the product category |

The backend assigns the `normal` strategy when creating a variant. Updating an existing variant preserves its current strategy.

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
| `catalog.view_productvariants` | GET products/{id}/variants, GET products/{id}/variant-form-options, GET variants, GET variants/{id} |
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
