from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
import time
import json
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, filename='interaction_log.log', filemode='w',
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_webdriver_options():
    """Configure browser options for visible interaction"""
    options = webdriver.FirefoxOptions()
    # Ensure browser is visible (non-headless)
    options.add_argument('--window-size=1920,1080')
    options.set_preference('javascript.enabled', True)  # Enable JavaScript
    return options

def log_action(action_type, element=None, value=None, url=None):
    """Log user interactions to a file"""
    action = {
        'timestamp': time.time(),
        'action_type': action_type,
        'element': element.get_attribute('outerHTML')[:200] if element else None,  # Truncate for brevity
        'value': value,
        'url': url or driver.current_url
    }
    logger.info(json.dumps(action, indent=2))
    with open('actions.json', 'a') as f:
        json.dump(action, f, indent=2)
        f.write('\n')

def record_interactions():
    """Launch Firefox and log user interactions"""
    global driver
    driver = webdriver.Firefox(options=get_webdriver_options())
    driver.set_page_load_timeout(30)
    driver.implicitly_wait(5)

    try:
        # Navigate to Tunisianet
        start_url = "https://www.tunisianet.com.tn"
        driver.get(start_url)
        log_action("navigate", url=start_url)
        print(f"Browser opened at {start_url}. Perform your actions manually.")

        # Keep the browser open and log interactions
        while True:
            try:
                # Wait for any clickable element interaction
                WebDriverWait(driver, 3600).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "*"))
                )
                # Log clicks
                elements = driver.find_elements(By.CSS_SELECTOR, "a, button, input, select")
                for element in elements:
                    try:
                        # Check if element was clicked
                        if element.is_displayed() and element.is_enabled():
                            driver.execute_script(
                                "arguments[0].addEventListener('click', function(e) { window.lastClicked = e.target; });",
                                element
                            )
                    except:
                        pass

                # Log form inputs
                inputs = driver.find_elements(By.CSS_SELECTOR, "input, textarea, select")
                for input_elem in inputs:
                    try:
                        if input_elem.is_displayed() and input_elem.is_enabled():
                            input_type = input_elem.get_attribute('type')
                            if input_type in ['text', 'email', 'password', 'textarea']:
                                value = input_elem.get_attribute('value')
                                if value:
                                    log_action("input", element=input_elem, value=value)
                            elif input_type in ['radio', 'checkbox']:
                                if input_elem.is_selected():
                                    log_action("select", element=input_elem, value=input_elem.get_attribute('id'))
                            elif input_elem.tag_name == 'select':
                                selected_option = input_elem.find_element(By.CSS_SELECTOR, "option[selected]")
                                log_action("select", element=input_elem, value=selected_option.text)
                    except:
                        pass

                time.sleep(1)  # Poll every second to avoid overloading
            except KeyboardInterrupt:
                print("Recording stopped by user.")
                break
            except Exception as e:
                logger.error(f"Error during interaction: {str(e)}")
                break

    finally:
        try:
            driver.quit()
            logger.info("Browser closed")
        except Exception as e:
            logger.warning(f"Error closing browser: {str(e)}")

if __name__ == "__main__":
    record_interactions()
