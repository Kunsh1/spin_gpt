from playwright.sync_api import sync_playwright
import time
import os
import pickle

# Path to save/load cookies
COOKIES_FILE = "chatgpt_cookies.pkl"

def save_cookies(context):
    cookies = context.cookies()
    with open(COOKIES_FILE, "wb") as f:
        pickle.dump(cookies, f)

def load_cookies(context):
    if os.path.exists(COOKIES_FILE):
        with open(COOKIES_FILE, "rb") as f:
            cookies = pickle.load(f)
            context.add_cookies(cookies)
        return True
    return False

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        page.goto("https://chatgpt.com/")
        page.wait_for_load_state("networkidle")
        time.sleep(3)  # give React time to render

        # Load cookies if present
        if load_cookies(context):
            page.reload()
            page.wait_for_load_state("networkidle")
            print("Loaded saved login cookies.")
        else:
            print("Please log in manually in the browser window that opened.")
            page.wait_for_selector("#prompt-textarea", timeout=0)  # wait indefinitely for login
            save_cookies(context)
            print("Login detected. Cookies saved for future sessions.")

        # Wait for the prompt textarea to be attached and scroll into view
        page.wait_for_selector("#prompt-textarea", state="attached", timeout=30000)
        page.locator("#prompt-textarea").scroll_into_view_if_needed()
        print("\nYou can now start chatting. Type 'exit' to quit.\n")

        known_div_count = len(page.query_selector_all("div.markdown"))

        while True:
            user_input = input("You: ")
            if user_input.lower() in ["exit", "quit"]:
                break

            # Capture fetch request for this prompt
            prompt_request = None
            def capture_request(request):
                nonlocal prompt_request
                if request.url.endswith("/conversation") or "backend-api" in request.url:
                    if request.method == "POST":
                        prompt_request = request
            context.on("request", capture_request)

            # Send input
            page.fill("div[contenteditable='true']", user_input)
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
                    print("[Warning] Timeout waiting for response.")
                    break

            # Update new divs
            all_divs = page.query_selector_all("div.markdown")
            new_divs = all_divs[known_div_count:]
            known_div_count = len(all_divs)

            # Stream content for each new div
            for div in new_divs:
                stable_count = 0
                if not hasattr(div, "printed_length"):
                    div.printed_length = 0  # global cursor per div

                while True:
                    current_text = div.inner_text()
                    if len(current_text) > div.printed_length:
                        new_text = current_text[div.printed_length:]

                        # Detect if code block
                        code_blocks = div.query_selector_all("pre, code")
                        if code_blocks:
                            for code in code_blocks:
                                if not hasattr(code, "printed_length"):
                                    code.printed_length = 0
                                code_text = code.inner_text()
                                if len(code_text) > code.printed_length:
                                    new_code = code_text[code.printed_length:]
                                    lang = code.get_attribute("class")
                                    if lang:
                                        lang = lang.split("language-")[-1].split()[0]
                                    else:
                                        lang = ""
                                    print(f"\n```{lang}\n{new_code}\n```\n", end="", flush=True)
                                    code.printed_length = len(code_text)
                        else:
                            # normal text
                            print(new_text, end="", flush=True)

                        div.printed_length = len(current_text)

                    # Check DOM stability
                    total_length = len(div.inner_text())
                    if hasattr(div, "prev_length"):
                        if total_length == div.prev_length:
                            stable_count += 1
                        else:
                            stable_count = 0
                        div.prev_length = total_length
                    else:
                        div.prev_length = total_length
                        stable_count = 0

                    # Stop streaming when fetch exists AND DOM stable for ~1 sec
                    if prompt_request and prompt_request.response() and stable_count >= 5:
                        print("\n")  # newline after response
                        break

                    time.sleep(0.2)

        browser.close()


if __name__ == "__main__":
    run()