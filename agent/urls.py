from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ProductViewSet, MerchantWebsiteViewSet,
    PriceComparisonViewSet, GovernorateViewSet,
    MerchantAccountViewSet, PurchaseOrderViewSet,
    login_view, register_view, start_order_view
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
    path('login/', login_view, name='login'),
    path('register/', register_view, name='register'),
    path('start-order/', start_order_view, name='start_order'),
]
