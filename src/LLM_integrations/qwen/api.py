import contextlib
import os

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

result = load_dotenv()
print(f".env loaded: {result}")  # True if found, False otherwise

TARGET_URL = "https://chat.qwen.ai/"
COOKIE_FILE_NAME = '.qwen_cookies.json'


class QwenApi:

    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self._initialized = False

    def start(self, headless: bool = False):
        """Start browser, load cookies, and log in once."""
        if self._initialized:
            return

        print(f'Starting session... {self.__class__.__name__}')

        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=headless)

        context_params = {'viewport':{"width": 1280, "height": 720}}
        if os.path.exists(COOKIE_FILE_NAME):
            context_params.update({'storage_state': COOKIE_FILE_NAME})
        self.context = self.browser.new_context(**context_params)
        self.page = self.context.new_page()

        self.page.goto(TARGET_URL)
        email = os.environ.get("QWEN_EMAIL")
        password = os.environ.get("QWEN_PASSWORD")
        if email and password:
            self._login(email, password)
        else:
            raise ValueError("QWEN_EMAIL and QWEN_PASSWORD must be set in .env")

        self._initialized = True

    def close(self):
        """Clean up browser resources."""
        if self.page:
            self.page.close()
        if self.context:
            self.context.close()
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()
        self._initialized = False

    def _login(self, username, password):
        login_button_css = 'span.qwen-chat-button-content'

        button = self.page.locator(login_button_css, has_text="Log in")
        self.page.wait_for_timeout(timeout=1234)
        logged = button.count() == 0
        if logged:
            print('We are logged in!')
            return
        button.click()
        self.page.wait_for_timeout(timeout=1234)
        email_input = self.page.locator('input[placeholder="Enter Your Email"]')
        password_input = self.page.locator('input[placeholder="Enter Your Password"]')

        print('Wait for Email field visible')  ## For debug
        email_input.wait_for(state="visible", timeout=10000)
        print('Email field visible')
        if email_input.count() > 0:
            email_input.type(username, delay=113)
            print("Email entered successfully")
        else:
            print("Email input field not found")

        if password_input.count() > 0:
            password_input.type(password, delay=111)
            print("Password entered successfully")
        else:
            print("Password input field not found")

        self.page.locator('button:has(span:has-text("Sign in"))').click()
        self.page.wait_for_timeout(timeout=1234)
        # Save cookies and storage to a file
        self.context.storage_state(path=COOKIE_FILE_NAME)

    def send_message(self, message: str) -> str:
        """Send a single message and return the full assistant response."""
        if not self._initialized:
            raise RuntimeError("QwenApi not started. Call start() first.")

        # Clear any stale state (optional: wait for new message area)
        textarea = self.page.locator('textarea.message-input-textarea')
        textarea.wait_for(state="visible", timeout=5000)
        textarea.fill(message)

        send_button = self.page.locator('button.send-button')
        send_button.click()

        self._wait_for_response_stable()
        last_response = self.page.locator(".qwen-chat-message-assistant").last.inner_text()
        last_response = last_response.replace('Thinking completed\n', '')
        return last_response

    def _wait_for_response_stable(
            self,
            selector=".qwen-chat-message-assistant",
            timeout=120_000,
            stable_ms=10_000
    ):
        """
        Waits for the last assistant message to stop changing.
        Returns the final text content.
        """
        self.page.wait_for_timeout(timeout=5000)
        # Initial wait, in case there is no any text generated and no thinking modal
        last_response = self.page.locator(selector).last

        # Get initial text
        previous_text = ""
        stable_time = 0
        poll_interval = 500  # ms
        thinking_completed_text = 'Thinking completed'

        start_time = self.page.evaluate("Date.now()")  # current time in ms
        thinking_text_box = self.page.locator(".qwen-chat-thinking-status-card-title-text")

        while True:
            try:
                current_text = last_response.inner_text(timeout=1000)
            except Exception:
                current_text = ""

            thinking_text = thinking_text_box.last.inner_text()
            if current_text == previous_text and thinking_text == thinking_completed_text:
                stable_time += poll_interval
            else:
                stable_time = 0
                previous_text = current_text

            # Check timeout
            elapsed = self.page.evaluate("Date.now()") - start_time
            if elapsed > timeout:
                raise TimeoutError(f"Response did not stabilize within {timeout}ms")

            if stable_time >= stable_ms:
                return current_text

            self.page.wait_for_timeout(poll_interval)
