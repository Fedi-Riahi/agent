from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ProductViewSet, MerchantWebsiteViewSet,
    PriceComparisonViewSet, GovernorateViewSet,
    MerchantAccountViewSet, PurchaseOrderViewSet
)

router = DefaultRouter()
router.register(r'products', ProductViewSet, basename='product')
router.register(r'merchant-websites', MerchantWebsiteViewSet, basename='merchant-website')
router.register(r'price-comparisons', PriceComparisonViewSet, basename='price-comparison')
router.register(r'governorates', GovernorateViewSet, basename='governorate')
router.register(r'merchant-accounts', MerchantAccountViewSet, basename='merchant-account')
router.register(r'orders/api', PurchaseOrderViewSet, basename='order')

urlpatterns = [
    path('', include(router.urls)),
]
