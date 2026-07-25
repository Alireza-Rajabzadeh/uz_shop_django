from django.contrib import admin
from unfold.admin import ModelAdmin
from .models.category import Category, CategoryStatus
from .models.category_detail import CategoryDetail
from .models.category_detail_relation import CategoryDetailRelation
from .models.product import Product, ProductStatus
from .models.product_details import ProductDetails
from .models.product_variants import ProductVariants
from .models.product_variants_details import ProductVariantsDetails


class CategoryDetailRelationInline(admin.TabularInline):
    model = CategoryDetailRelation
    extra = 1
    autocomplete_fields = ["detail"]


@admin.register(Category)
class CategoryAdmin(ModelAdmin):
    list_display = ["name", "parent", "status"]
    list_filter = ["status"]
    search_fields = ["name"]
    inlines = [CategoryDetailRelationInline]


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


class ProductVariantsDetailsInline(admin.TabularInline):
    model = ProductVariantsDetails
    extra = 1
    autocomplete_fields = ["detail"]


@admin.register(ProductVariants)
class ProductVariantAdmin(ModelAdmin):
    list_display = ["product", "sku", "price"]
    list_filter = ["product"]
    search_fields = ["sku"]
    inlines = [ProductVariantsDetailsInline]


@admin.register(ProductVariantsDetails)
class ProductVariantDetailsAdmin(ModelAdmin):
    list_display = ["variant", "detail", "value"]
    list_filter = ["variant"]
    autocomplete_fields = ["variant", "detail"]
