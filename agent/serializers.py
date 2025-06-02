from rest_framework import serializers
from .models import (
    Product, MerchantWebsite, PriceComparison,
    PurchaseOrder, Governorate, MerchantAccount
)
from django.contrib.auth import get_user_model

User = get_user_model()

class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = '__all__'

class MerchantWebsiteSerializer(serializers.ModelSerializer):
    class Meta:
        model = MerchantWebsite
        fields = '__all__'

class PriceComparisonSerializer(serializers.ModelSerializer):
    website = MerchantWebsiteSerializer(read_only=True)

    class Meta:
        model = PriceComparison
        fields = '__all__'

class GovernorateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Governorate
        fields = '__all__'

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name']

class MerchantAccountSerializer(serializers.ModelSerializer):
    website = MerchantWebsiteSerializer(read_only=True)

    class Meta:
        model = MerchantAccount
        fields = '__all__'
        extra_kwargs = {
            'encrypted_password': {'write_only': True},
            'cookies': {'write_only': True}
        }

class PurchaseOrderSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    product = ProductSerializer(read_only=True)
    selected_website = MerchantWebsiteSerializer(read_only=True)
    governorate = GovernorateSerializer(read_only=True)

    class Meta:
        model = PurchaseOrder
        fields = '__all__'
        read_only_fields = [
            'status', 'created_at', 'completed_at',
            'konnect_payment_id', 'payment_status'
        ]

    def validate_contact_phone(self, value):
        if not value.startswith('+216'):
            raise serializers.ValidationError("Phone must be Tunisian (+216)")
        return value
