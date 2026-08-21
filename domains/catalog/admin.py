from django.contrib import admin
from unfold.admin import ModelAdmin
from .models.brand import Brand, BrandCategory
from .models.category import Category, CategoryStatus
from .models.category_detail import CategoryDetail, CategoryDetailOption
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
from .services.detail_service import DetailService


class BrandCategoryInline(admin.TabularInline):
    model = BrandCategory
    extra = 1
    autocomplete_fields = ["category"]


@admin.register(Brand)
class BrandAdmin(ModelAdmin):
    list_display = ["name", "slug", "fa_name"]
    search_fields = ["name", "fa_name"]
    readonly_fields = ["slug"]
    inlines = [BrandCategoryInline]


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
    list_display = ["name", "slug", "fa_name", "parent", "status"]
    list_filter = ["status"]
    search_fields = ["name", "fa_name"]
    readonly_fields = ["slug"]
    inlines = [CategoryDetailRelationInline, CategoryVariantAttributeInline]


@admin.register(CategoryStatus)
class CategoryStatusAdmin(ModelAdmin):
    list_display = ["name"]


@admin.register(CategoryDetail)
class CategoryDetailAdmin(ModelAdmin):
    list_display = ["name", "type", "required", "filterable"]
    list_filter = ["type", "required", "filterable"]
    search_fields = ["name"]

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        DetailService._sync_options(obj)


@admin.register(CategoryDetailOption)
class CategoryDetailOptionAdmin(ModelAdmin):
    list_display = ["name", "detail", "position"]
    list_filter = ["detail"]
    search_fields = ["name", "detail__name"]
    autocomplete_fields = ["detail"]


@admin.register(CategoryDetailRelation)
class CategoryDetailRelationAdmin(ModelAdmin):
    list_display = ["category", "detail", "value"]
    list_filter = ["category"]
    autocomplete_fields = ["category", "detail"]


class ProductDetailsInline(admin.TabularInline):
    model = ProductDetails
    extra = 1
    autocomplete_fields = ["detail", "option"]


class ProductVariantInline(admin.TabularInline):
    model = ProductVariants
    extra = 1
    show_change_link = True


@admin.register(Product)
class ProductAdmin(ModelAdmin):
    list_display = ["name", "slug", "brand", "categories_display", "status"]
    list_filter = ["brand", "categories", "status"]
    search_fields = ["name"]
    autocomplete_fields = ["brand"]
    readonly_fields = ["slug"]
    filter_horizontal = ["categories"]
    inlines = [ProductDetailsInline, ProductVariantInline]

    @admin.display(description="categories")
    def categories_display(self, obj):
        return ", ".join(
            obj.categories.order_by("id").values_list("name", flat=True)
        )


@admin.register(ProductStatus)
class ProductStatusAdmin(ModelAdmin):
    list_display = ["name"]


@admin.register(ProductDetails)
class ProductDetailAdmin(ModelAdmin):
    list_display = ["product", "detail", "value"]
    list_filter = ["product"]
    autocomplete_fields = ["product", "detail", "option"]


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
    list_display = ["name", "fa_name"]
    search_fields = ["name", "fa_name"]
    inlines = [VariantOptionInline]


@admin.register(VariantOption)
class VariantOptionAdmin(ModelAdmin):
    list_display = ["name", "fa_name", "info", "attribute", "sku_code"]
    list_filter = ["attribute"]
    search_fields = ["name", "fa_name", "info", "sku_code"]
    autocomplete_fields = ["attribute"]


@admin.register(CategoryVariantAttribute)
class CategoryVariantAttributeAdmin(ModelAdmin):
    list_display = ["category", "attribute"]
    autocomplete_fields = ["category", "attribute"]
