from playwright.sync_api import sync_playwright
import time

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        page.goto("https://chatgpt.com/")
        page.wait_for_load_state("domcontentloaded")
        time.sleep(3)

        # Close login popup if present
        try:
            page.locator("button[aria-label='Close'], button:has(svg)").first.click(timeout=5000)
            print("Login popup closed.")
        except:
            pass

        # Wait for textarea
        page.wait_for_selector("#prompt-textarea", timeout=20000)
        print("You can now start chatting. Type 'exit' to quit.\n")

        # Track known markdown divs
        known_div_count = len(page.query_selector_all("div.markdown"))

        while True:
            user_input = input("You: ")
            if user_input.lower() in ["exit", "quit"]:
                break

            # Send input
            page.fill("#prompt-textarea", user_input)
            page.keyboard.press("Enter")

            # Wait for new markdown div
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

            # Get new divs
            all_divs = page.query_selector_all("div.markdown")
            new_divs = all_divs[known_div_count:]
            known_div_count = len(all_divs)

            # Stream content by element type
            for div in new_divs:
                printed_elements = set()
                while True:
                    elements = div.query_selector_all("p, pre, code")
                    new_elements = []
                    for el in elements:
                        text = el.inner_text()
                        if text not in printed_elements:
                            new_elements.append((el, text))
                            printed_elements.add(text)

                    if new_elements:
                        for el, text in new_elements:
                            tag = el.evaluate("el => el.tagName.toLowerCase()")
                            if tag == "pre" or tag == "code":
                                # Wrap code blocks in triple backticks
                                print(f"\n```\n{text}\n```\n")
                            else:
                                # Normal paragraph
                                print(text + "\n")
                    else:
                        # If all elements printed, check if done streaming
                        if len(elements) == len(printed_elements):
                            break
                    time.sleep(0.3)

        browser.close()

if __name__ == "__main__":
    run()