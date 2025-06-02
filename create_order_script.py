from django.contrib.auth.models import User
from agent.models import Product, Governorate, PurchaseOrder
from agent.tasks import initiate_purchase_task
import time

def run_test_order():
    # Create or get test user
    try:
        user, created = User.objects.get_or_create(
            username='testuser',
            defaults={
                'email': 'kaiba.work@gmail.com',
                'password': 'Kaiba123654'
            }
        )
        if created:
            user.set_password('Kaiba123654')
            user.save()
        print(f"{'Created new user' if created else 'Retrieved existing user'}: {user.username}")
    except Exception as e:
        print(f"Error creating/retrieving user: {e}")
        raise

    # Create or get product
    try:
        product, created = Product.objects.get_or_create(
            name="pc portable asus tuf gaming a15 fa506nf",
            defaults={
                'description': 'pc portable asus tuf gaming a15',
                'manufacturer': 'Asus'
            }
        )
        print(f"{'Created new product' if created else 'Retrieved existing product'}: {product.name}")
    except Exception as e:
        print(f"Error creating/retrieving product: {e}")
        raise

    # Get first available governorate
    try:
        governorate = Governorate.objects.first()
        if not governorate:
            raise ValueError("No governorates found in database")
        print(f"Selected governorate: {governorate.name}")
    except Exception as e:
        print(f"Error retrieving governorate: {e}")
        raise

    # Create purchase order
    try:
        order = PurchaseOrder.objects.create(
            user=user,
            product=product,
            shipping_address="456 Avenue Habib Bourguiba, Tunis",
            contact_phone="+21698765432",
            governorate=governorate,
            status="PENDING"
        )
        print(f"Created order: {order.id}")
    except Exception as e:
        print(f"Error creating order: {e}")
        raise

    # Initiate purchase process
    try:
        result = initiate_purchase_task.delay(order.id)
        print(f"Initiated purchase task for order: {order.id}")

        # Wait for task to complete with timeout
        timeout = 300  # 5 minutes
        start_time = time.time()

        while not result.ready() and (time.time() - start_time) < timeout:
            time.sleep(5)
            print("Waiting for task to complete...")

        if result.ready():
            print(f"Task completed with result: {result.get()}")
        else:
            print("Task timed out")

    except Exception as e:
        print(f"Error initiating purchase task: {e}")
        raise

if __name__ == "__main__":
    run_test_order()
