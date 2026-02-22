import asyncio
import os
import pickle
import json
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

COOKIES_FILE = "chatgpt_cookies.pkl"

# Global state
playwright = None
browser = None
context = None
page = None
# browser_lock = asyncio.Lock()
browser_lock = None
active_queue = None  # Will hold the queue for the current active request

async def save_cookies():
    cookies = await context.cookies()
    with open(COOKIES_FILE, "wb") as f:
        pickle.dump(cookies, f)

async def load_cookies():
    if os.path.exists(COOKIES_FILE):
        with open(COOKIES_FILE, "rb") as f:
            cookies = pickle.load(f)
            await context.add_cookies(cookies)
        return True
    return False

# --- Exposed Python Callbacks ---
async def py_print_chunk(text):
    if active_queue:
        await active_queue.put(text)

async def py_stream_done():
    if active_queue:
        await active_queue.put("[DONE]")

# --- Self-Healing Mechanism ---
async def check_and_heal_session():
    """Checks if the chat box is ready. If not, attempts to reload or bypass checks."""
    try:
        # Check if the text box is visible and ready
        is_ready = await page.is_visible("#prompt-textarea", timeout=2000)
        if is_ready:
            return True
            
        print("[Auto-Heal] Chat box not found. Attempting to refresh session...")
        await page.goto("https://chatgpt.com/")
        await page.wait_for_load_state("domcontentloaded")
        await asyncio.sleep(2)
        
        # Check if we got hit by Cloudflare or logged out
        if await page.is_visible("#prompt-textarea"):
            print("[Auto-Heal] Session restored successfully.")
            return True
        else:
            print("[Auto-Heal] FAILED. You may need to manually log in or pass a CAPTCHA.")
            return False
    except Exception as e:
        print(f"[Auto-Heal] Error during healing: {e}")
        return False

# --- FastAPI Lifespan (Startup / Shutdown) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    global playwright, browser, context, page, browser_lock
    browser_lock = asyncio.Lock()
    
    playwright = await async_playwright().start()
    # Use stealthy args to bypass Turnstile
    browser = await playwright.chromium.launch(
        headless=True,
        args=["--disable-blink-features=AutomationControlled"]
    )
    context = await browser.new_context(
        viewport={"width": 1280, "height": 800},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
    )
    page = await context.new_page()
    
    # Apply playwright-stealth to hide the fact that this is a bot
    stealth = Stealth()
    await stealth.apply_stealth_async(context)
    
    print("Navigating to ChatGPT...")
    await page.goto("https://chatgpt.com/")
    await page.wait_for_load_state("domcontentloaded")
    
    if await load_cookies():
        await page.reload()
        await page.wait_for_load_state("domcontentloaded")
        print("Cookies loaded.")
    else:
        print("WARNING: No cookies found. You must log in manually first!")
        
    await page.expose_function("py_print_chunk", py_print_chunk)
    await page.expose_function("py_stream_done", py_stream_done)

    # Inject the Fetch Interceptor (Same as before, adapted for async context)
    await page.evaluate("""
        (() => {
            const origFetch = window.fetch;
            window.fetch = async (...args) => {
                const response = await origFetch(...args);
                try {
                    const url = args[0] instanceof Request ? args[0].url : args[0];
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
                                    buffer = lines.pop(); 
                                    for (let line of lines) {
                                        line = line.trim();
                                        if (line.startsWith('data: ')) {
                                            const jsonText = line.slice(6).trim();
                                            if (jsonText === "[DONE]") {
                                                window.py_stream_done();
                                                continue;
                                            }
                                            try {
                                                const data = JSON.parse(jsonText);
                                                if (data && Array.isArray(data.v)) {
                                                    data.v.forEach(patch => {
                                                        if (patch.o === "append" && 
                                                            typeof patch.p === 'string' && 
                                                            patch.p.includes("/message/content/parts/0")) {
                                                            window.py_print_chunk(patch.v);
                                                        }
                                                    });
                                                }
                                            } catch(e) {}
                                        }
                                    }
                                }
                            } catch (err) {}
                        })();
                    }
                } catch(e) {}
                return response;
            };
        })();
    """)
    
    yield # App is running here
    
    # Teardown
    await browser.close()
    await playwright.stop()

app = FastAPI(lifespan=lifespan)

# --- The API Endpoint ---
@app.get("/api/chat")
async def chat(prompt: str):
    global active_queue
    
    if not prompt.strip():
        return {"error": "Prompt cannot be empty"}

    # 1. Acquire the lock so only ONE request uses the browser at a time
    await browser_lock.acquire()
    
    # 2. Set up the queue for this specific request
    active_queue = asyncio.Queue()
    
    try:
        # 3. Heal session if necessary
        is_healthy = await check_and_heal_session()
        if not is_healthy:
            browser_lock.release()
            return {"error": "Session is broken or requires CAPTCHA verification."}
            
        # 4. Send the prompt
        # 4. Send the prompt (with React-safe delays)
        print(f"[API] Preparing to send prompt: {prompt[:30]}...")
        
        # Give the ChatGPT UI a moment to fully reset from the previous turn
        await asyncio.sleep(1.0) 
        
        chat_box = page.locator("div[contenteditable='true']")
        
        # Click into it to ensure focus
        await chat_box.click() 
        
        # Fill the text
        await chat_box.fill(prompt)
        
        # CRITICAL: Wait a split second for React's internal state to update 
        # and turn the Send button from gray (disabled) to black (enabled)
        await asyncio.sleep(0.5)
        
        # Now fire the Enter key
        await page.keyboard.press("Enter")
        print("[API] Prompt sent, waiting for stream...")
        
    except Exception as e:
        browser_lock.release()
        return {"error": str(e)}

    # 5. Generator to stream the queue back to the API caller
    async def event_generator():
        timeout_seconds = 60
        try:
            while True:
                # Wait for the next chunk from the JS interceptor with a timeout
                chunk = await asyncio.wait_for(active_queue.get(), timeout=timeout_seconds)
                
                if chunk == "[DONE]":
                    break
                    
                # Yield the raw chunk as an SSE event
                yield f"data: {json.dumps({'text': chunk})}\n\n"
                
        except asyncio.TimeoutError:
            yield f"data: {json.dumps({'error': 'Stream timed out'})}\n\n"
        finally:
            # CRITICAL: We MUST release the lock here after the stream finishes,
            # so the next user in line can use the browser!
            browser_lock.release()

    return StreamingResponse(event_generator(), media_type="text/event-stream")
# python -m uvicorn api:app --host 0.0.0.0 --port 8000    