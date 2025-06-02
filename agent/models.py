from django.db import models
from django.contrib.auth import get_user_model
from django.core.validators import RegexValidator, MinValueValidator
from django.utils import timezone
from django.contrib.auth.hashers import make_password, check_password
from django.core.validators import URLValidator

User = get_user_model()

class TunisianPhoneField(models.CharField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('max_length', 15)
        kwargs.setdefault('validators', [
            RegexValidator(
                regex=r'^\+216\d{8}$',
                message="Phone number must be in the format +216XXXXXXXX"
            )
        ])
        super().__init__(*args, **kwargs)

class Governorate(models.Model):
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=2, unique=True)
    delivery_surcharge = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=0.00,
        help_text="Additional delivery cost for this governorate"
    )

    def __str__(self):
        return f"{self.name} ({self.code})"

class MerchantAccount(models.Model):
    ACCOUNT_TYPES = [
        ('SELLER', 'Seller Account'),
        ('AFFILIATE', 'Affiliate Account'),
        ('API', 'API Access'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='merchant_accounts')
    website = models.ForeignKey('MerchantWebsite', on_delete=models.CASCADE)
    account_type = models.CharField(max_length=20, choices=ACCOUNT_TYPES, default='SELLER')
    username = models.CharField(max_length=100)
    encrypted_password = models.CharField(max_length=255)
    cookies = models.JSONField(blank=True, null=True)
    is_verified = models.BooleanField(default=False)
    last_login = models.DateTimeField(null=True, blank=True)
    api_key = models.CharField(max_length=255, blank=True, null=True)
    rate_limit = models.PositiveIntegerField(default=10, help_text="Requests per minute")
    is_active = models.BooleanField(default=True)

    def set_password(self, raw_password):
        self.encrypted_password = make_password(raw_password)

    def check_password(self, raw_password):
        return check_password(raw_password, self.encrypted_password)

    class Meta:
        unique_together = ('user', 'website', 'account_type')
        verbose_name = "Merchant Account"
        verbose_name_plural = "Merchant Accounts"

class ProductCategory(models.Model):
    name = models.CharField(max_length=255, unique=True)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True)
    description = models.TextField(blank=True)
    keywords = models.JSONField(default=list, help_text="List of search keywords for this category")

    def __str__(self):
        return self.name

class Product(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    category = models.ForeignKey(ProductCategory, on_delete=models.SET_NULL, null=True)
    manufacturer = models.CharField(max_length=100, blank=True)
    model_number = models.CharField(max_length=50, blank=True)
    specifications = models.JSONField(default=dict)
    image_url = models.URLField(blank=True, validators=[URLValidator()])
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.model_number})" if self.model_number else self.name

class MerchantWebsite(models.Model):
    WEBSITE_TYPES = [
        ('ECOMMERCE', 'E-commerce Platform'),
        ('MARKETPLACE', 'Online Marketplace'),
        ('RETAILER', 'Retailer Website'),
    ]

    name = models.CharField(max_length=255, unique=True)
    base_url = models.URLField(unique=True)
    website_type = models.CharField(max_length=20, choices=WEBSITE_TYPES, default='ECOMMERCE')
    requires_login = models.BooleanField(default=False)
    supports_guest_checkout = models.BooleanField(default=False)
    scraping_config = models.JSONField()
    active = models.BooleanField(default=True)
    priority = models.PositiveSmallIntegerField(
        default=1,
        help_text="Priority for scraping (higher numbers are scraped first)"
    )
    last_scraped = models.DateTimeField(null=True, blank=True)
    scraping_interval = models.PositiveIntegerField(
        default=3600,
        help_text="Minimum seconds between scrapes"
    )

    def __str__(self):
        return f"{self.name} ({self.get_website_type_display()})"

class PriceComparison(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='price_comparisons')
    website = models.ForeignKey(MerchantWebsite, on_delete=models.CASCADE)
    price = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        validators=[MinValueValidator(0)]
    )
    original_price = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)]
    )
    currency = models.CharField(max_length=3, default='TND')
    timestamp = models.DateTimeField(auto_now_add=True)
    availability = models.BooleanField(default=True)
    availability_text = models.CharField(max_length=100, blank=True)
    delivery_days = models.PositiveSmallIntegerField(null=True, blank=True)
    shipping_cost = models.DecimalField(
        max_digits=8,
        decimal_places=3,
        default=0,
        validators=[MinValueValidator(0)]
    )
    product_url = models.URLField(max_length=500, blank=True, validators=[URLValidator()])
    image_url = models.URLField(max_length=500, blank=True, validators=[URLValidator()])
    discount_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Calculated discount percentage"
    )
    warranty = models.CharField(max_length=100, blank=True)
    stock_quantity = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ['timestamp']
        get_latest_by = 'timestamp'
        unique_together = ('product', 'website', 'timestamp')
        verbose_name = "Price Comparison"
        verbose_name_plural = "Price Comparisons"

    def save(self, *args, **kwargs):
        # Calculate discount percentage if original price exists
        if self.original_price and self.original_price > 0 and self.price < self.original_price:
            self.discount_percentage = round(
                ((self.original_price - self.price) / self.original_price) * 100,
                2
            )
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.product.name} @ {self.website.name}: {self.price} {self.currency}"

class PurchaseOrder(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('AWAITING_CONFIRMATION', 'Awaiting Confirmation'),
        ('PROCESSING', 'Processing'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
        ('CANCELLED', 'Cancelled'),
    ]

    PAYMENT_METHODS = [
        ('KONNECT', 'Konnect'),
        ('CARD', 'Credit Card'),
        ('CASH', 'Cash on Delivery'),
        ('INSTALLMENT', 'Installment'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='orders')
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    selected_website = models.ForeignKey(MerchantWebsite, on_delete=models.PROTECT, null=True, blank=True)
    final_price = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)]
    )
    status = models.CharField(max_length=25, choices=STATUS_CHOICES, default='PENDING')
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, default='KONNECT')
    konnect_payment_id = models.CharField(max_length=100, blank=True)
    payment_status = models.CharField(max_length=50, blank=True)
    payment_response = models.JSONField(null=True, blank=True)
    shipping_address = models.TextField()
    contact_phone = TunisianPhoneField()
    governorate = models.ForeignKey(Governorate, on_delete=models.PROTECT)
    special_instructions = models.TextField(blank=True)
    is_business = models.BooleanField(default=False)
    business_registration = models.CharField(max_length=50, blank=True)
    tracking_number = models.CharField(max_length=100, blank=True)
    tracking_url = models.URLField(blank=True)
    estimated_delivery = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['user', 'created_at']),
        ]

    def __str__(self):
        return f"Order #{self.id} - {self.product.name} ({self.get_status_display()})"

class AgentDecisionLog(models.Model):
    order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name='decision_logs')
    decision_reason = models.TextField()
    considered_options = models.JSONField()
    gemini_response = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    execution_time = models.FloatField(help_text="Decision time in seconds")
    confidence_score = models.FloatField(
        null=True,
        blank=True,
        help_text="AI confidence in the decision (0-1)"
    )
    alternatives_considered = models.PositiveIntegerField(default=0)
    metadata = models.JSONField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Agent Decision Log"
        verbose_name_plural = "Agent Decision Logs"

    def __str__(self):
        return f"Decision for Order #{self.order.id} at {self.created_at}"

class ScrapingSession(models.Model):
    website = models.ForeignKey(MerchantWebsite, on_delete=models.CASCADE)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=[
        ('RUNNING', 'Running'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
    ], default='RUNNING')
    products_scraped = models.PositiveIntegerField(default=0)
    new_products_found = models.PositiveIntegerField(default=0)
    price_changes_detected = models.PositiveIntegerField(default=0)
    errors_encountered = models.PositiveIntegerField(default=0)
    session_log = models.TextField(blank=True)

    def __str__(self):
        return f"Scraping session for {self.website.name} at {self.started_at}"
