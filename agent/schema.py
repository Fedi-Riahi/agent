import graphene
from graphene_django import DjangoObjectType
from graphene_django.filter import DjangoFilterConnectionField
from .models import (
    Product, MerchantWebsite, PriceComparison,
    PurchaseOrder, Governorate
)
from graphql_jwt.decorators import login_required

class ProductType(DjangoObjectType):
    class Meta:
        model = Product
        interfaces = (graphene.relay.Node,)
        filter_fields = {
            'name': ['exact', 'icontains'],
            'category': ['exact']
        }

class MerchantWebsiteType(DjangoObjectType):
    class Meta:
        model = MerchantWebsite
        interfaces = (graphene.relay.Node,)
        filter_fields = {
            'name': ['exact', 'icontains'],
            'active': ['exact']
        }

class PriceComparisonType(DjangoObjectType):
    class Meta:
        model = PriceComparison
        interfaces = (graphene.relay.Node,)
        filter_fields = {
            'product__name': ['exact'],
            'website__name': ['exact']
        }

class GovernorateType(DjangoObjectType):
    class Meta:
        model = Governorate
        interfaces = (graphene.relay.Node,)

class PurchaseOrderType(DjangoObjectType):
    class Meta:
        model = PurchaseOrder
        interfaces = (graphene.relay.Node,)
        filter_fields = {
            'status': ['exact'],
            'product__name': ['exact']
        }

class Query(graphene.ObjectType):
    product = graphene.relay.Node.Field(ProductType)
    all_products = DjangoFilterConnectionField(ProductType)

    merchant_website = graphene.relay.Node.Field(MerchantWebsiteType)
    all_merchant_websites = DjangoFilterConnectionField(MerchantWebsiteType)

    price_comparison = graphene.relay.Node.Field(PriceComparisonType)
    all_price_comparisons = DjangoFilterConnectionField(PriceComparisonType)

    governorate = graphene.relay.Node.Field(GovernorateType)
    all_governorates = DjangoFilterConnectionField(GovernorateType)

    purchase_order = graphene.relay.Node.Field(PurchaseOrderType)
    my_orders = DjangoFilterConnectionField(PurchaseOrderType)

    @login_required
    def resolve_my_orders(self, info, **kwargs):
        return PurchaseOrder.objects.filter(user=info.context.user)

class CreatePurchaseOrder(graphene.Mutation):
    class Arguments:
        product_id = graphene.ID(required=True)
        website_id = graphene.ID()
        shipping_address = graphene.String(required=True)
        contact_phone = graphene.String(required=True)
        governorate_id = graphene.ID(required=True)
        special_instructions = graphene.String()
        is_business = graphene.Boolean()
        business_registration = graphene.String()

    order = graphene.Field(PurchaseOrderType)

    @login_required
    def mutate(self, info, product_id, shipping_address, contact_phone, governorate_id, **kwargs):
        from .models import Product, Governorate
        from .tasks import initiate_purchase_task

        product = Product.objects.get(id=product_id)
        governorate = Governorate.objects.get(id=governorate_id)

        order = PurchaseOrder.objects.create(
            user=info.context.user,
            product=product,
            shipping_address=shipping_address,
            contact_phone=contact_phone,
            governorate=governorate,
            **{k: v for k, v in kwargs.items() if v is not None}
        )

        initiate_purchase_task.delay(order.id)
        return CreatePurchaseOrder(order=order)

class Mutation(graphene.ObjectType):
    create_purchase_order = CreatePurchaseOrder.Field()

schema = graphene.Schema(query=Query, mutation=Mutation)
