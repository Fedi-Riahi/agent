import json
import os
import re
import time
from decimal import Decimal
from urllib.parse import urljoin
from datetime import timedelta
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (TimeoutException, NoSuchElementException,
                                      WebDriverException, ElementNotInteractableException)
from celery import shared_task
from celery.utils.log import get_task_logger
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from agent.models import (
    Product, MerchantWebsite, PriceComparison,
    PurchaseOrder, AgentDecisionLog
)
import stripe

logger = get_task_logger(__name__)

# Configure Gemini API
genai.configure(api_key=settings.GEMINI_API_KEY, transport='rest')
model = genai.GenerativeModel('gemini-1.5-flash')

# Configure Stripe
stripe.api_key = settings.STRIPE_SECRET_KEY

# Suppress TensorFlow warnings
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

def convert_currency(amount, from_currency, to_currency):
    """Convert between currencies using fixed rates."""
    if from_currency == to_currency:
        return amount
    rates = {
        'USD': {'USD': 1.0, 'TND': 3.1},
        'EUR': {'USD': 1.1, 'TND': 3.3},
        'TND': {'USD': 1/3.1, 'EUR': 1/3.3}
    }
    return amount * rates.get(from_currency, {}).get(to_currency, 1.0)

def estimate_delivery(website):
    """Estimate delivery time based on website."""
    if 'tunisianet' in website.base_url.lower():
        return 3
    elif 'megapc.tn' in website.base_url.lower():
        return 3
    return 5

def estimate_shipping(website, product_price):
    """Calculate shipping costs based on website policies."""
    price = float(product_price or 0)
    if 'tunisianet' in website.base_url.lower() or 'megapc.tn' in website.base_url.lower():
        return 7.0 if price < 500 else 0.0
    return 10.0

def sanitize_gemini_response(text):
    """Extract JSON from potentially malformed Gemini response."""
    if not text:
        raise ValueError("Empty response from Gemini")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        patterns = [
            r'```json\n({.*?})\n```',
            r'```\n({.*?})\n```',
            r'({.*})'
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    continue
        raise ValueError(f"No valid JSON found in response: {text[:200]}...")

def get_webdriver_options():
    """Configure Firefox options for web scraping."""
    options = webdriver.FirefoxOptions()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1080')
    options.set_preference('permissions.default.image', 2)
    options.set_preference('javascript.enabled', False)
    return options

def scrape_tunisianet_product(driver, website, product):
    """Scrape product information from Tunisianet search results."""
    try:
        search_url = urljoin(website.base_url, f"recherche?controller=search&s={product.name}")
        logger.info(f"Scraping Tunisianet at {search_url}")
        driver.get(search_url)

        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".products.row .product-miniature"))
        )
        time.sleep(2)

        soup = BeautifulSoup(driver.page_source, 'html.parser')
        items = soup.select(".products.row .product-miniature")[:5]

        if not items:
            logger.warning(f"No items found on Tunisianet for {product.name}")
            return None

        for item in items:
            try:
                title_elem = item.select_one(".product-title a")
                price_elem = item.select_one(".product-price-and-shipping .price")
                regular_price_elem = item.select_one(".product-price-and-shipping .regular-price")
                availability_elem = item.select_one(".product-availability")
                image_elem = item.select_one(".product-thumbnail img")
                url_elem = item.select_one(".product-title a")

                if not title_elem or not price_elem:
                    continue

                title = title_elem.text.strip()
                price_text = price_elem.text.strip()
                price_text_clean = price_text.replace('DT', '').replace('\xa0', '').replace(' ', '').replace(',', '.')
                price = float(price_text_clean)

                original_price = price
                if regular_price_elem:
                    original_price_text = regular_price_elem.text.strip()
                    original_price_clean = original_price_text.replace('DT', '').replace('\xa0', '').replace(' ', '').replace(',', '.')
                    original_price = float(original_price_clean)

                product_url = urljoin(website.base_url, url_elem['href']) if url_elem else None
                availability = True
                if availability_elem:
                    availability_text = availability_elem.text.strip().lower()
                    availability = "en stock" in availability_text or "disponible" in availability_text

                PriceComparison.objects.update_or_create(
                    product=product,
                    website=website,
                    defaults={
                        'price': price,
                        'original_price': original_price,
                        'availability': availability,
                        'delivery_days': estimate_delivery(website),
                        'shipping_cost': estimate_shipping(website, price),
                        'product_url': product_url,
                        'image_url': image_elem['src'] if image_elem else None,
                        'timestamp': timezone.now()
                    }
                )
                logger.info(f"Successfully scraped {title} from Tunisianet")
                return True

            except Exception as e:
                logger.warning(f"Error parsing item on Tunisianet: {str(e)}")
                continue

    except Exception as e:
        logger.error(f"Error scraping Tunisianet: {str(e)}")
        raise

def scrape_megapc_product(driver, website, product):
    """Scrape product information from MegaPC search results."""
    try:
        search_url = urljoin(website.base_url, f"recherche?controller=search&s={product.name}")
        logger.info(f"Scraping MegaPC at {search_url}")
        driver.get(search_url)

        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".product-miniature"))
        )
        time.sleep(2)

        soup = BeautifulSoup(driver.page_source, 'html.parser')
        items = soup.select(".product-miniature")[:5]

        if not items:
            logger.warning(f"No items found on MegaPC for {product.name}")
            return None

        for item in items:
            try:
                title_elem = item.select_one(".product-title a")
                price_elem = item.select_one(".price")
                availability_elem = item.select_one(".availability")
                image_elem = item.select_one(".product-image img")
                url_elem = item.select_one(".product-title a")

                if not title_elem or not price_elem:
                    continue

                title = title_elem.text.strip()
                price_text = price_elem.text.strip()
                price_match = re.search(r'([\d,.]+)\s*DT', price_text.replace(',', ''))
                if not price_match:
                    continue
                price = float(price_match.group(1).replace(',', ''))

                product_url = urljoin(website.base_url, url_elem['href']) if url_elem else None
                availability = True
                if availability_elem:
                    availability = "En stock" in availability_elem.text or "Disponible" in availability_elem.text

                PriceComparison.objects.update_or_create(
                    product=product,
                    website=website,
                    defaults={
                        'price': price,
                        'original_price': price,
                        'availability': availability,
                        'delivery_days': estimate_delivery(website),
                        'shipping_cost': estimate_shipping(website, price),
                        'product_url': product_url,
                        'image_url': image_elem['src'] if image_elem else None,
                        'timestamp': timezone.now()
                    }
                )
                logger.info(f"Successfully scraped {title} from MegaPC")
                return True

            except Exception as e:
                logger.warning(f"Error parsing item on MegaPC: {str(e)}")
                continue

    except Exception as e:
        logger.error(f"Error scraping MegaPC: {str(e)}")
        raise

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def scrape_product_prices(self, product_id):
    """Scrape product prices from multiple Tunisian e-commerce sites."""
    product = Product.objects.get(id=product_id)
    websites = MerchantWebsite.objects.filter(active=True)

    for website in websites:
        retry_count = 0
        max_retries = 2
        success = False
        driver = None
        try:
            cache_key = f"price_{website.id}_{product.id}"
            if cache.get(cache_key):
                logger.info(f"Using cached price for {website.name}")
                continue

            driver = webdriver.Firefox(options=get_webdriver_options())
            driver.set_page_load_timeout(30)
            driver.implicitly_wait(5)

            if 'tunisianet' in website.base_url.lower():
                success = scrape_tunisianet_product(driver, website, product)
            elif 'megapc.tn' in website.base_url.lower():
                success = scrape_megapc_product(driver, website, product)
            else:
                logger.warning(f"Skipping unsupported website: {website.name}")
                continue

            if success:
                cache.set(cache_key, True, 3600)

        except (WebDriverException, TimeoutException) as e:
            retry_count += 1
            logger.error(f"Error scraping {website.name}: {str(e)}")
            if retry_count >= max_retries:
                logger.error(f"Marking {website.name} as inactive after {max_retries} retries")
                website.active = False
                website.save()
            raise self.retry(exc=e, countdown=5 * retry_count)
        except Exception as e:
            logger.error(f"Unexpected error scraping {website.name}: {str(e)}")
            raise self.retry(exc=e, countdown=5 * retry_count)
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception as e:
                    logger.warning(f"Error closing browser: {str(e)}")

@shared_task(bind=True, max_retries=3, default_retry_delay=120)
def initiate_purchase_task(self, order_id):
    """Initiate purchase workflow with AI decision-making and proceed to completion."""
    order = PurchaseOrder.objects.select_related(
        'product', 'selected_website', 'user', 'governorate'
    ).get(id=order_id)

    try:
        if order.status != 'PENDING':
            raise ValueError(f"Order {order_id} is not in PENDING status")

        # Scrape prices if no website is selected
        if not order.selected_website:
            scrape_product_prices.delay(order.product.id)
            comparisons = PriceComparison.objects.filter(
                product=order.product,
                timestamp__gte=timezone.now() - timedelta(hours=2)
            ).order_by('price')

            if not comparisons.exists():
                raise ValueError("No available pricing data")

            prompt = prepare_decision_prompt(order, comparisons)
            logger.info(f"Gemini Prompt:\n{prompt}")
            response = model.generate_content(prompt)
            decision = sanitize_gemini_response(response.text)
            validate_decision(decision, comparisons)

            selected_website = next(
                (c for c in comparisons if c.website_id == decision['selected_website_id']),
                None
            )
            if not selected_website:
                raise ValueError(f"Selected website ID {decision['selected_website_id']} not in available options")

            # Update order with selected website and price
            order.selected_website_id = decision['selected_website_id']
            order.final_price = Decimal(str(decision['final_price_TND']))
            order.save()

            def decimal_default(obj):
                if isinstance(obj, Decimal):
                    return float(obj)
                raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

            AgentDecisionLog.objects.create(
                order=order,
                decision_reason=decision['decision_summary'],
                considered_options=json.dumps(
                    list(comparisons.values('id', 'website_id', 'price', 'original_price')),
                    default=decimal_default
                ),
                gemini_response=json.dumps(decision, default=decimal_default),
                execution_time=response.candidates[0].finish_reason == 'STOP' and 0.0 or response.usage_metadata.total_token_count / 1000
            )

            # Directly proceed to complete_purchase_task
            complete_purchase_task.delay(order.id)
            logger.info(f"Order {order.id} proceeding to completion")
            return f"Order {order.id} initiated and proceeding to completion with website {selected_website.website.name} and price {decision['final_price_TND']} TND"

        else:
            raise ValueError("Order already has a selected website")

    except Exception as e:
        order.status = 'FAILED'
        order.error_message = str(e)[:200]
        order.save()
        logger.error(f"Order {order_id} failed: {str(e)}", exc_info=True)
        raise self.retry(exc=e)

@shared_task(bind=True, max_retries=3, default_retry_delay=120)
def complete_purchase_task(self, order_id):
    """Complete purchase with enhanced error handling."""
    order = PurchaseOrder.objects.select_related(
        'product', 'selected_website', 'user', 'governorate'
    ).get(id=order_id)

    try:
        if order.status != 'PENDING':
            raise ValueError(f"Order {order_id} is not in PENDING status")

        selected_website = PriceComparison.objects.filter(
            product=order.product,
            website_id=order.selected_website_id,
            timestamp__gte=timezone.now() - timedelta(hours=2)
        ).order_by('price').first()

        if not selected_website:
            raise ValueError(f"No valid price data for selected website {order.selected_website_id}")

        if 'tunisianet' in order.selected_website.base_url.lower():
            try:
                place_tunisianet_order(order, selected_website)
                order.status = 'COMPLETED'
                order.completed_at = timezone.now()
                order.save()
                logger.info(f"Order {order.id} placed successfully on Tunisianet")
                return f"Order {order.id} completed successfully"
            except Exception as e:
                logger.error(f"Order placement failed: {str(e)}", exc_info=True)
                order.status = 'FAILED'
                order.error_message = str(e)[:200]
                order.save()
                raise self.retry(exc=e)
        else:
            raise ValueError("Order placement only supported for Tunisianet")

    except Exception as e:
        logger.error(f"Order {order_id} failed: {str(e)}", exc_info=True)
        order.status = 'FAILED'
        order.error_message = str(e)[:200]
        order.save()
        raise self.retry(exc=e)

def place_tunisianet_order(order, comparison):
    """Automate order placement on Tunisianet's checkout flow."""
    driver = None
    try:
        options = get_webdriver_options()
        options.set_preference('javascript.enabled', True)
        driver = webdriver.Firefox(options=options)
        driver.set_page_load_timeout(30)
        driver.implicitly_wait(5)

        # Step 1: Add product to cart
        product_url = comparison.product_url
        if not product_url:
            raise ValueError("Product URL not available")
        logger.info(f"Navigating to product page: {product_url}")
        driver.get(product_url)
        WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, ".add-to-cart"))
        )

        add_to_cart_button = driver.find_element(By.CSS_SELECTOR, ".add-to-cart")
        if add_to_cart_button.get_attribute("disabled"):
            raise ValueError("Add to cart button is disabled")
        driver.execute_script("arguments[0].click();", add_to_cart_button)
        logger.info("Clicked 'Add to Cart'")

        # Step 2: Handle cart modal and proceed to checkout
        max_attempts = 3
        attempt = 0
        checkout_button = None
        while attempt < max_attempts:
            try:
                WebDriverWait(driver, 30).until(
                    EC.visibility_of_element_located((By.CSS_SELECTOR, ".modal-dialog .modal-content"))
                )
                logger.info("Cart modal opened")

                try:
                    cookie_popup = driver.find_element(By.CSS_SELECTOR, ".cookie-notice, .popup, button.close, .modal .close")
                    driver.execute_script("arguments[0].click();", cookie_popup)
                    logger.info("Closed interfering popup")
                    time.sleep(1)
                except NoSuchElementException:
                    pass

                selectors = [
                    (By.CSS_SELECTOR, "a.btn.btn-primary.btn-block[href*='panier?action=show']"),
                    (By.XPATH, "//a[contains(@href, 'panier?action=show') and contains(@class, 'btn-primary')]"),
                    (By.CSS_SELECTOR, ".modal-content .cart-content-btn a.btn.btn-primary"),
                    (By.CSS_SELECTOR, "a.btn.btn-primary")
                ]
                for by, selector in selectors:
                    try:
                        checkout_button = WebDriverWait(driver, 10).until(
                            EC.element_to_be_clickable((by, selector))
                        )
                        logger.debug(f"Found Commander button: {checkout_button.get_attribute('outerHTML')}")
                        break
                    except TimeoutException:
                        logger.warning(f"Selector {selector} not found")
                        continue

                if checkout_button:
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", checkout_button)
                    time.sleep(0.5)
                    if checkout_button.get_attribute("disabled"):
                        raise ValueError("Commander button is disabled")
                    driver.execute_script("arguments[0].click();", checkout_button)
                    logger.info("Clicked 'Commander' to proceed to checkout")
                    break
                else:
                    raise TimeoutException("No valid checkout button found in modal")

            except (TimeoutException, ElementNotInteractableException) as e:
                attempt += 1
                logger.warning(f"Attempt {attempt}/{max_attempts} failed: {str(e)}")
                if attempt < max_attempts:
                    driver.get("https://www.tunisianet.com.tn/panier?action=show")
                    WebDriverWait(driver, 15).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "body"))
                    )
                    logger.info("Navigated to cart page as fallback")
                    try:
                        checkout_button = WebDriverWait(driver, 10).until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, "a[href*='/commande']"))
                        )
                        driver.execute_script("arguments[0].click();", checkout_button)
                        logger.info("Clicked checkout button on cart page")
                        break
                    except TimeoutException:
                        driver.refresh()
                        WebDriverWait(driver, 15).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, "body"))
                        )
                        driver.get(product_url)
                        WebDriverWait(driver, 15).until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, ".add-to-cart"))
                        )
                        add_to_cart_button = driver.find_element(By.CSS_SELECTOR, ".add-to-cart")
                        if not add_to_cart_button.get_attribute("disabled"):
                            driver.execute_script("arguments[0].click();", add_to_cart_button)
                            logger.info("Re-clicked 'Add to Cart' after refresh")
                        time.sleep(2)
                else:
                    raise TimeoutException(f"Failed to find checkout button after {max_attempts} attempts")

        # Step 3: Proceed to checkout page
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.ID, "checkout-login-form"))
        )
        logger.info("Reached checkout page")

        # Step 4: Login
        try:
            cookie_popup = driver.find_element(By.CSS_SELECTOR, ".cookie-notice, .popup, button.close")
            driver.execute_script("arguments[0].click();", cookie_popup)
            logger.info("Closed interfering popup before login")
            time.sleep(1)
        except NoSuchElementException:
            pass

        login_form = driver.find_element(By.ID, "login-form")
        email_input = login_form.find_element(By.NAME, "email")
        password_input = login_form.find_element(By.NAME, "password")
        submit_button = login_form.find_element(By.CSS_SELECTOR, "button[data-link-action='sign-in']")

        # Use hardcoded email and password for Tunisianet login
        email = ""
        password = ""

        logger.debug(f"Attempting login with email: {email[:8]}****{email[-4:]}")
        email_input.clear()
        email_input.send_keys(email)
        password_input.clear()
        password_input.send_keys(password)
        driver.execute_script("arguments[0].click();", submit_button)
        logger.info("Submitted login form")

        try:
            error_element = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".alert.alert-danger"))
            )
            error_message = error_element.text.strip()
            logger.error(f"Login error detected: {error_message}")
            if "invalid" in error_message.lower() or "incorrect" in error_message.lower():
                raise ValueError(f"Login failed: {error_message}")
        except TimeoutException:
            pass

        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "checkout-addresses-step"))
            )
            logger.info("Login successful, reached address step")
        except TimeoutException:
            try:
                captcha_element = driver.find_element(By.CSS_SELECTOR, "iframe[src_id='referrer-policy'], .same-origin")
                logger.error("Security error detected, manual intervention required")
                raise ValueError("Login failed: Security error")
            except NoSuchElementException:
                raise ValueError("Login failed: Did not reach address step")

        # Step 5: Address step
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.ID, "checkout-addresses-step"))
        )
        logger.info("Reached address step, using saved address")

        try:
            submit_address_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button[name='confirm-addresses']"))
            )
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", submit_address_button)
            driver.execute_script("arguments[0].click();", submit_address_button)
            logger.info("Submitted address step with saved address")
        except TimeoutException:
            logger.info("No address confirmation button found, checking for delivery step")
            try:
                WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.ID, "checkout-delivery-step"))
                )
                logger.info("Automatically transitioned to delivery step")
            except TimeoutException:
                raise ValueError("Failed to proceed past address step")

        # Step 6: Delivery step
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.ID, "checkout-delivery-step"))
        )
        logger.info("Reached delivery step")

        try:
            popup = driver.find_element(By.CSS_SELECTOR, ".cookie-notice, .popup, button.close, .modal .close")
            driver.execute_script("arguments[0].click();", popup)
            logger.info("Closed interfering popup on delivery step")
            time.sleep(1)
        except NoSuchElementException:
            pass

        try:
            delivery_form = WebDriverWait(driver, 20).until(
                EC.visibility_of_element_located((By.ID, "js-delivery"))
            )
            logger.info("Found delivery form with id='js-delivery'")
        except TimeoutException:
            raise ValueError("Failed to locate delivery form with id='js-delivery'")

        try:
            submit_delivery_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button[name='confirmDeliveryOption']"))
            )
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", submit_delivery_button)
            driver.execute_script("arguments[0].click();", submit_delivery_button)
            logger.info("Clicked 'Continuer' button on delivery step")
        except TimeoutException:
            raise ValueError("Failed to locate or click 'Continuer' button")

        # Step 7: Payment step
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.ID, "checkout-payment-step"))
        )
        logger.info("Reached payment step")

        payment_form = driver.find_element(By.ID, "payment-confirmation")
        payment_option = driver.find_element(By.ID, "payment-option-3")
        driver.execute_script("arguments[0].click();", payment_option)
        logger.info("Selected 'Cash on Delivery' payment option")

        terms_checkbox = driver.find_element(By.ID, "conditions_to_approve[terms-and-conditions]")
        if not terms_checkbox.is_selected():
            driver.execute_script("arguments[0].click();", terms_checkbox)
            logger.info("Accepted terms and conditions")

        finalize_button = payment_form.find_element(By.CSS_SELECTOR, "button.btn.btn-primary.center-block")
        if finalize_button.get_attribute("disabled"):
            raise ValueError("Finalize order button is disabled")
        driver.execute_script("arguments[0].click();", finalize_button)
        logger.info("Clicked 'Finalizei votre commande'")

        max_attempts = 2
        attempt = 0
        while attempt < max_attempts:
            try:
                WebDriverWait(driver, 30).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".order-confirmation, .confirmation, [class*='confirm']"))
                )
                logger.info("Order successfully placed")
                break
            except TimeoutException:
                attempt += 1
                if attempt == max_attempts:
                    raise
                driver.refresh()
                time.sleep(2)

    except (TimeoutException, NoSuchElementException, ElementNotInteractableException) as e:
        logger.error(f"Browser interaction error: {str(e)}", exc_info=True)
        if driver:
            with open(f"error_page_source_{order.id}.html", "w", encoding="utf-8") as f:
                f.write(driver.page_source)
            driver.save_screenshot(f"error_screenshot_{order.id}.png")
        raise
    except Exception as e:
        logger.error(f"Unexpected error during order placement: {str(e)}", exc_info=True)
        if driver:
            with open(f"error_page_source_{order.id}.html", "w", encoding="utf-8") as f:
                f.write(driver.page_source)
            driver.save_screenshot(f"error_screenshot_{order.id}.png")
        raise
    finally:
        if driver:
            try:
                driver.quit()
            except Exception as e:
                logger.warning(f"Error closing browser: {str(e)}")

def prepare_decision_prompt(order, comparisons):
    """Generate prompt for AI decision-making."""
    options = []
    for comp in comparisons:
        options.append({
            'website_id': comp.website.id,
            'website_name': comp.website.name,
            'price_TND': float(comp.price),
            'original_price_TND': float(comp.original_price),
            'delivery_days': comp.delivery_days,
            'shipping_cost': float(comp.shipping_cost),
            'total_cost': float(comp.price + comp.shipping_cost),
            'timestamp': comp.timestamp.isoformat(),
            'product_url': comp.product_url or '',
            'availability': comp.availability
        })

    if not options:
        raise ValueError("No valid options for decision")

    return f"""You are an AI purchasing agent. Return ONLY valid JSON with these EXACT keys:
{{
    "selected_website_id": (integer ID from options),
    "final_price_TND": (float total price in TND),
    "decision_summary": (string explaining your choice)
}}

Product: {order.product.name}
Delivery to: {order.governorate.name}
Business Purchase: {'Yes' if order.is_business else 'No'}

Available Options:
{json.dumps(options, indent=2)}

Decision Criteria (in order of priority):
1. Lowest total cost (price + shipping) in TND
2. Fastest delivery time to {order.governorate.name}
3. Most recent price data (check timestamp)
4. Merchant reliability (prefer known merchants like Tunisianet, MyTek)
5. Product availability

RULES:
- You MUST select one of the available options
- selected_website_id MUST match a website_id from the options
- final_price_TND must be the total cost (price + shipping)
- decision_summary should clearly explain your choice
- Consider discounts (difference between original_price_TND and price_TND)

Return ONLY the JSON object without any additional text or markdown formatting.
"""

def validate_decision(decision, comparisons=None):
    """Validate AI decision structure and content."""
    if not isinstance(decision, dict):
        raise ValueError("Decision must be a dictionary")

    required_keys = {
        'selected_website_id': int,
        'final_price_TND': (int, float),
        'decision_summary': str
    }

    for key, typ in required_keys.items():
        if key not in decision:
            raise ValueError(f"Missing required key: {key}")
        if not isinstance(decision[key], typ):
            raise ValueError(f"Invalid type for {key}. Expected {typ}, got {type(decision[key])}")

    if comparisons is not None:
        valid_ids = {c.website_id for c in comparisons}
        if decision['selected_website_id'] not in valid_ids:
            raise ValueError(f"Selected website ID {decision['selected_website_id']} not in valid options")

def process_stripe_payment(order):
    """Process payment through Stripe API."""
    try:
        amount_cents = int(float(order.final_price) * 100)
        charge = stripe.Charge.create(
            amount=amount_cents,
            currency="tnd",
            source="tok_visa",
            description=f"Order #{order.id} - {order.product.name}",
            metadata={
                "order_id": str(order.id),
                "product": order.product.name,
                "website_id": str(order.selected_website_id)
            }
        )

        order.stripe_payment_id = charge.id
        order.payment_status = 'SUCCESS' if charge.paid else 'FAILED'
        order.payment_response = {
            "id": charge.id,
            "amount": charge.amount / 100,
            "currency": charge.currency,
            "status": charge.status
        }
        order.save()
        return charge

    except stripe.error.StripeError as e:
        error_msg = f"Stripe error: {e.user_message if hasattr(e, 'user_message') else str(e)}"
        logger.error(error_msg)
        order.payment_status = 'FAILED'
        order.error_message = error_msg
        order.payment_response = {'error': error_msg}
        order.save()
        raise ValueError(error_msg)
