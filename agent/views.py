from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login
from django.contrib.auth.models import User
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

def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('start_order')
        else:
            return render(request, 'login.html', {'error': 'Invalid username or password'})
    return render(request, 'login.html')

def register_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')
        if password != confirm_password:
            return render(request, 'register.html', {'error': 'Passwords do not match'})
        if User.objects.filter(username=username).exists():
            return render(request, 'register.html', {'error': 'Username already taken'})
        if User.objects.filter(email=email).exists():
            return render(request, 'register.html', {'error': 'Email already registered'})
        user = User.objects.create_user(username=username, email=email, password=password)
        login(request, user)
        return redirect('start_order')
    return render(request, 'register.html')

def start_order_view(request):
    if not request.user.is_authenticated:
        return redirect('login')
    if request.method == 'POST':
        product_name = request.POST.get('product_name').strip()
        governorate_id = request.POST.get('governorate')
        is_business = request.POST.get('is_business') == 'on'
        if not product_name:
            return render(request, 'start_order.html', {
                'error': 'Product name is required',
                'governorates': Governorate.objects.all()
            })
        try:
            governorate = Governorate.objects.get(id=governorate_id)
            # Get or create product
            product, created = Product.objects.get_or_create(
                name=product_name,
                defaults={'category': 'Other'}  # Default category
            )
            order = PurchaseOrder.objects.create(
                user=request.user,
                product=product,
                governorate=governorate,
                is_business=is_business,
                status='PENDING'
            )
            initiate_purchase_task.delay(order.id)
            return redirect('start_order')  # Replace with orders view if added
        except Governorate.DoesNotExist:
            return render(request, 'start_order.html', {
                'error': 'Invalid governorate',
                'governorates': Governorate.objects.all()
            })
        except Exception as e:
            return render(request, 'start_order.html', {
                'error': f'Error creating order: {str(e)}',
                'governorates': Governorate.objects.all()
            })
    return render(request, 'start_order.html', {
        'governorates': Governorate.objects.all()
    })

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
