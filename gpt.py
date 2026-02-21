from playwright.sync_api import sync_playwright
import time
import os
import pickle
import json

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
        # Set headless=False if you need to manually log in for the first time
        browser = p.chromium.launch(headless=True) 
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        
        print("Navigating to ChatGPT...")
        page.goto("https://chatgpt.com/")
        page.wait_for_load_state("domcontentloaded") # Fixed: No more networkidle timeouts
        time.sleep(2)

        # Load cookies if present
        if load_cookies(context):
            page.reload()
            page.wait_for_load_state("domcontentloaded")
            print("Loaded saved login cookies.")
        else:
            print("Please log in manually in the browser window that opened.")
            page.wait_for_selector("#prompt-textarea", timeout=0)
            save_cookies(context)
            print("Login detected. Cookies saved for future sessions.")

        page.wait_for_selector("#prompt-textarea", state="attached", timeout=30000)
        
        # --- Python to JS Communication Setup ---
        
        # 1. Print function
        def print_chunk(text):
            print(text, end="", flush=True)
        page.expose_function("py_print_chunk", print_chunk)

        # 2. State management to fix the delay bug
        stream_state = {"is_streaming": False}
        
        def set_stream_done():
            stream_state["is_streaming"] = False
        page.expose_function("py_stream_done", set_stream_done)

        # --- Inject the Fetch Interceptor ---
        page.evaluate("""
            (() => {
                const origFetch = window.fetch;
                window.fetch = async (...args) => {
                    const response = await origFetch(...args);
                    try {
                        const url = args[0] instanceof Request ? args[0].url : args[0];
                        
                        // Target the conversation stream
                        if (typeof url === 'string' && url.includes('conversation')) {
                            const clone = response.clone(); 
                            
                            (async () => {
                                try {
                                    const reader = clone.body.getReader();
                                    const decoder = new TextDecoder();
                                    let buffer = ''; 
                                    
                                    while (true) {
                                        const { value, done } = await reader.read();
                                        if (done) break;
                                        
                                        buffer += decoder.decode(value, { stream: true });
                                        const lines = buffer.split('\\n');
                                        buffer = lines.pop(); // Keep incomplete JSON in the buffer
                                        
                                        for (let line of lines) {
                                            line = line.trim();
                                            if (line.startsWith('data: ')) {
                                                const jsonText = line.slice(6).trim();
                                                
                                                // Trigger the Python event loop to break!
                                                if (jsonText === "[DONE]") {
                                                    window.py_stream_done();
                                                    continue;
                                                }
                                                
                                                try {
                                                    const data = JSON.parse(jsonText);
                                                    
                                                    // Parse the append operations
                                                    if (data && Array.isArray(data.v)) {
                                                        data.v.forEach(patch => {
                                                            if (patch.o === "append" && 
                                                                typeof patch.p === 'string' && 
                                                                patch.p.includes("/message/content/parts/0")) {
                                                                
                                                                window.py_print_chunk(patch.v);
                                                            }
                                                        });
                                                    }
                                                } catch(e) {
                                                    // Ignore JSON parse errors for non-JSON lines
                                                }
                                            }
                                        }
                                    }
                                } catch (err) {
                                    console.error("Stream reader error:", err);
                                }
                            })();
                        }
                    } catch(e) {}
                    return response;
                };
            })();
        """)

        print("\nYou can now start chatting. Type 'exit' to quit.\n")

        # --- Main Chat Loop ---
        while True:
            user_input = input("You: ")
            if user_input.lower() in ["exit", "quit"]:
                break

            # 1. FIX: Prevent empty inputs from triggering the hang
            if not user_input.strip():
                print("Skipping empty input.\n")
                continue

            stream_state["is_streaming"] = True 

            page.fill("div[contenteditable='true']", user_input)
            page.keyboard.press("Enter")

            # 2. FIX: Add a failsafe timeout (e.g., 60 seconds)
            timeout_seconds = 60
            start_time = time.time()

            while stream_state["is_streaming"]:
                page.wait_for_timeout(50)
                
                # If we've waited too long, break out to save the script
                if time.time() - start_time > timeout_seconds:
                    print("\n[Error: Network timeout or no response from server.]")
                    stream_state["is_streaming"] = False 
                    break
            
            print("\n")  # Newline after the complete response

        browser.close()

if __name__ == "__main__":
    run()