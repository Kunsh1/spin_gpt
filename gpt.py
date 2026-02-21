from playwright.sync_api import sync_playwright
import time

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        page.goto("https://chatgpt.com/")
        page.wait_for_load_state("domcontentloaded")
        time.sleep(3)  # wait for popup

        # Try closing login popup
        try:
            page.locator("button[aria-label='Close'], button:has(svg)").first.click(timeout=5000)
            print("Login popup closed.")
        except:
            pass

        # Wait for textarea
        page.wait_for_selector("#prompt-textarea", timeout=20000)
        print("You can now start chatting. Type 'exit' to quit.\n")

        # Track how many markdown divs already exist
        known_div_count = len(page.query_selector_all("div.markdown"))

        while True:
            user_input = input("You: ")
            if user_input.lower() in ["exit", "quit"]:
                break

            # Type input and send
            page.fill("#prompt-textarea", user_input)
            page.keyboard.press("Enter")

            # Wait until a new markdown div appears
            timeout = 30
            elapsed = 0
            while True:
                all_divs = page.query_selector_all("div.markdown")
                if len(all_divs) > known_div_count:
                    break
                time.sleep(0.2)
                elapsed += 0.2
                if elapsed > timeout:
                    print("Timeout waiting for response.")
                    break

            # Update known_div_count and get the new div
            all_divs = page.query_selector_all("div.markdown")
            new_divs = all_divs[known_div_count:]
            known_div_count = len(all_divs)

            # Stream new content in real time
            for div in new_divs:
                printed_length = 0
                stable_polls = 0
                while True:
                    current_text = div.inner_text()
                    if len(current_text) > printed_length:
                        # Print only the new portion
                        print(current_text[printed_length:], end='', flush=True)
                        printed_length = len(current_text)
                        stable_polls = 0  # reset counter when new text appears
                    else:
                        stable_polls += 1
                        if stable_polls >= 5:  # ~1 second of no growth
                            print("\n")  # finish line
                            break
                    time.sleep(0.2)

        browser.close()

if __name__ == "__main__":
    run()