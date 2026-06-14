from django.contrib import admin



# Register your models here.
from .models.category import Category, CategoryStatus
from .models.category_detail import CategoryDetail
from .models.category_detail_relation import CategoryDetailRelation
from .models.product import Product, ProductStatus
from .models.product_details import ProductDetails
from .models.product_variants import ProductVariants
from .models.product_variants_details import ProductVariantsDetails

admin.site.register(Category)
admin.site.register(CategoryStatus)
admin.site.register(CategoryDetail)
admin.site.register(CategoryDetailRelation)
admin.site.register(Product)
admin.site.register(ProductStatus)
admin.site.register(ProductDetails)
admin.site.register(ProductVariants)
admin.site.register(ProductVariantsDetails)