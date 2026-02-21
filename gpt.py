from playwright.sync_api import sync_playwright
import time

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        page.goto("https://chatgpt.com/")
        page.wait_for_load_state("domcontentloaded")

        # Give popup time to appear
        time.sleep(3)

        # 🔥 Aggressive popup close detection
        try:
            page.locator(
                "button[aria-label='Close'], button:has(svg)"
            ).first.click(timeout=5000)
            print("Login popup closed.")
        except:
            print("No login popup detected.")

        # Wait for prompt textarea
        page.wait_for_selector("#prompt-textarea", timeout=20000)

        # Type message
        page.fill("#prompt-textarea", "cccdcd")

        # Send message
        page.keyboard.press("Enter")

        # Wait for first response block
        page.wait_for_selector("div.markdown", timeout=30000)

        # Wait for streaming to finish (basic way)
        time.sleep(6)

        # Get latest response
        responses = page.query_selector_all("div.markdown")
        latest_response = responses[-1].inner_text()

        print("\n=== RESPONSE ===\n")
        print(latest_response)

        browser.close()

if __name__ == "__main__":
    run()