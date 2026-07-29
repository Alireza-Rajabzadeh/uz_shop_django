from django.contrib import admin
from unfold.admin import ModelAdmin
from .models.category import Category, CategoryStatus
from .models.category_detail import CategoryDetail
from .models.category_detail_relation import CategoryDetailRelation
from .models.product import Product, ProductStatus
from .models.product_file import ProductFile
from .models.product_details import ProductDetails
from .models.product_variants import ProductVariants
from .models.product_variant_selection import ProductVariantSelection
from .models.variant_attribute import (
    CategoryVariantAttribute,
    VariantAttribute,
    VariantOption,
)


class CategoryDetailRelationInline(admin.TabularInline):
    model = CategoryDetailRelation
    extra = 1
    autocomplete_fields = ["detail"]


class CategoryVariantAttributeInline(admin.TabularInline):
    model = CategoryVariantAttribute
    extra = 1
    autocomplete_fields = ["attribute"]


@admin.register(Category)
class CategoryAdmin(ModelAdmin):
    list_display = ["name", "parent", "status"]
    list_filter = ["status"]
    search_fields = ["name"]
    inlines = [CategoryDetailRelationInline, CategoryVariantAttributeInline]


@admin.register(CategoryStatus)
class CategoryStatusAdmin(ModelAdmin):
    list_display = ["name"]


@admin.register(CategoryDetail)
class CategoryDetailAdmin(ModelAdmin):
    list_display = ["name", "type", "required", "filterable"]
    list_filter = ["type", "required", "filterable"]
    search_fields = ["name"]


@admin.register(CategoryDetailRelation)
class CategoryDetailRelationAdmin(ModelAdmin):
    list_display = ["category", "detail", "value"]
    list_filter = ["category"]
    autocomplete_fields = ["category", "detail"]


class ProductDetailsInline(admin.TabularInline):
    model = ProductDetails
    extra = 1
    autocomplete_fields = ["detail"]


class ProductVariantInline(admin.TabularInline):
    model = ProductVariants
    extra = 1
    show_change_link = True


@admin.register(Product)
class ProductAdmin(ModelAdmin):
    list_display = ["name", "category", "status"]
    list_filter = ["category", "status"]
    search_fields = ["name"]
    inlines = [ProductDetailsInline, ProductVariantInline]


@admin.register(ProductStatus)
class ProductStatusAdmin(ModelAdmin):
    list_display = ["name"]


@admin.register(ProductDetails)
class ProductDetailAdmin(ModelAdmin):
    list_display = ["product", "detail", "value"]
    list_filter = ["product"]
    autocomplete_fields = ["product", "detail"]


@admin.register(ProductFile)
class ProductFileAdmin(ModelAdmin):
    list_display = ["product", "file", "role", "position", "is_primary"]
    list_filter = ["role", "is_primary"]
    search_fields = ["product__name", "file__original_name"]
    readonly_fields = [
        "product", "file", "role", "position", "is_primary", "alt_text",
        "created_at", "updated_at",
    ]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class ProductVariantSelectionInline(admin.TabularInline):
    model = ProductVariantSelection
    extra = 1
    autocomplete_fields = ["attribute", "option"]


@admin.register(ProductVariants)
class ProductVariantAdmin(ModelAdmin):
    list_display = ["product", "sku", "price"]
    list_filter = ["product"]
    search_fields = ["sku"]
    readonly_fields = ["sku", "combination_key"]
    inlines = [ProductVariantSelectionInline]


@admin.register(ProductVariantSelection)
class ProductVariantSelectionAdmin(ModelAdmin):
    list_display = ["variant", "attribute", "option"]
    list_filter = ["variant"]
    autocomplete_fields = ["variant", "attribute", "option"]


class VariantOptionInline(admin.TabularInline):
    model = VariantOption
    extra = 1


@admin.register(VariantAttribute)
class VariantAttributeAdmin(ModelAdmin):
    list_display = ["name"]
    search_fields = ["name"]
    inlines = [VariantOptionInline]


@admin.register(VariantOption)
class VariantOptionAdmin(ModelAdmin):
    list_display = ["name", "attribute", "sku_code"]
    list_filter = ["attribute"]
    search_fields = ["name", "sku_code"]
    autocomplete_fields = ["attribute"]


@admin.register(CategoryVariantAttribute)
class CategoryVariantAttributeAdmin(ModelAdmin):
    list_display = ["category", "attribute"]
    autocomplete_fields = ["category", "attribute"]
