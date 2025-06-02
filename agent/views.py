from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.utils import timezone
from datetime import timedelta
from .models import (
    Product, MerchantWebsite, PriceComparison,
    PurchaseOrder, Governorate, MerchantAccount
)
from .serializers import (
    ProductSerializer, MerchantWebsiteSerializer,
    PriceComparisonSerializer, PurchaseOrderSerializer,
    GovernorateSerializer, MerchantAccountSerializer
)
from .tasks import initiate_purchase_task
import google.generativeai as genai
from django.conf import settings

# Configure Gemini API
genai.configure(api_key=settings.GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-pro')

class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['category']
    permission_classes = [IsAuthenticated]

class MerchantWebsiteViewSet(viewsets.ModelViewSet):
    queryset = MerchantWebsite.objects.filter(active=True)
    serializer_class = MerchantWebsiteSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['requires_login', 'supports_guest_checkout']
    permission_classes = [IsAuthenticated]

class PriceComparisonViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = PriceComparisonSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['product', 'website']
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return PriceComparison.objects.filter(
            timestamp__gte=timezone.now() - timedelta(hours=24)
        ).order_by('price')

class GovernorateViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Governorate.objects.all()
    serializer_class = GovernorateSerializer
    permission_classes = [IsAuthenticated]

class MerchantAccountViewSet(viewsets.ModelViewSet):
    serializer_class = MerchantAccountSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return MerchantAccount.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

class PurchaseOrderViewSet(viewsets.ModelViewSet):
    serializer_class = PurchaseOrderSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return PurchaseOrder.objects.filter(user=self.request.user).order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=True, methods=['post'])
    def initiate_purchase(self, request, pk=None):
        order = self.get_object()
        if order.status != 'PENDING':
            return Response(
                {'error': 'Order already processed'},
                status=status.HTTP_400_BAD_REQUEST
            )
        initiate_purchase_task.delay(order.id)
        return Response(
            {'status': 'Purchase process initiated'},
            status=status.HTTP_202_ACCEPTED
        )
