from django.contrib import admin
from .models import (
    Governorate,
    MerchantAccount,
    Product,
    MerchantWebsite,
    PriceComparison,
    PurchaseOrder,
    AgentDecisionLog
)

@admin.register(Governorate)
class GovernorateAdmin(admin.ModelAdmin):
    list_display = ('name', 'code')
    search_fields = ('name',)

@admin.register(MerchantWebsite)
class MerchantWebsiteAdmin(admin.ModelAdmin):
    list_display = ('name', 'base_url', 'active')
    list_filter = ('active',)
    search_fields = ('name', 'base_url')

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'category')
    search_fields = ('name', 'category')
    list_filter = ('category',)

@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'product', 'status', 'created_at')
    list_filter = ('status', 'governorate')
    search_fields = ('product__name', 'contact_phone')
    date_hierarchy = 'created_at'

@admin.register(AgentDecisionLog)
class AgentDecisionLogAdmin(admin.ModelAdmin):
    list_display = ('order', 'created_at')
    readonly_fields = ('created_at',)

# For sensitive models
@admin.register(MerchantAccount)
class MerchantAccountAdmin(admin.ModelAdmin):
    list_display = ('user', 'website', 'is_verified')
    exclude = ('encrypted_password', 'cookies')  # Don't show sensitive fields
