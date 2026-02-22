# 🚀 ChatGPT Web-to-API Wrapper (Real-Time SSE Streaming)

A robust, self-healing, asynchronous Python API that reverse-engineers the official ChatGPT web interface.

Instead of dealing with clunky DOM scraping or massive delays, this project **intercepts the raw Server-Sent Events (SSE) network stream** in real-time. It wraps the entire process in a highly concurrent FastAPI server, allowing you to use your standard ChatGPT web account as a programmatic, streaming API.

⚠️ **Disclaimer:** *This project is for educational purposes and personal use only. Automating the ChatGPT web interface violates OpenAI's Terms of Service. Use this responsibly. You are responsible for any account bans that may occur.*

## ✨ Key Features

* **Zero DOM Scraping:** Intercepts the underlying `/backend-api/conversation` fetch requests directly for 100% accurate token extraction.
* **True Real-Time Streaming:** Streams tokens back to the client the millisecond they arrive via SSE (exactly like the official API).
* **Self-Healing Sessions:** Automatically detects expired sessions or missing text boxes and attempts to refresh the page.
* **Cloudflare Stealth:** Integrates `playwright-stealth` (V2) to strip webdriver fingerprints and bypass basic Turnstile checks.
* **Concurrency Safe:** Uses `asyncio.Lock()` to ensure that multiple API requests queue up cleanly instead of mashing the browser keyboard simultaneously.
* **Smart Metadata Parsing:** Automatically strips or formats OpenAI's hidden internal routing tags (e.g., `entity...`).
* **Docker Ready:** Built for headless server deployment using a "Cookie Smuggler" volume mount strategy.

---

## 🧠 How It Works

Instead of reading the HTML `<div>` tags (which causes duplicate text and timing issues), this script injects a custom JavaScript `fetch` interceptor into the Playwright browser.

It clones the OpenAI network stream, buffers the byte chunks to prevent network-split JSON errors, and extracts the exact `{"o": "append"}` delta patches. It then signals Python the exact moment the `[DONE]` flag is received, resulting in perfect, delay-free turn-taking.

---

## 💻 Local Installation & Setup

### 1. Install Dependencies

Ensure you have Python 3.10+ installed, then run:

```bash
pip install fastapi uvicorn playwright playwright-stealth requests
playwright install chromium

```

### 2. Generate Your Authentication Cookies

Before running the API headless, you need to log in manually to generate the session cookies.

1. Open `api.py`.
2. Temporarily set `headless=False` in the browser launch arguments.
3. Run the script: `python api.py`
4. Log into your ChatGPT account in the browser window that opens.
5. Once logged in, the script will save `data/chatgpt_cookies.pkl`. Close the script and set `headless=True` again.

### 3. Start the API Server

```bash
uvicorn api:app --host 0.0.0.0 --port 8000

```

---

## 🐳 Docker Deployment (For Remote Servers)

Servers don't have screens, so you cannot log in manually if a CAPTCHA appears. We solve this by smuggling the session cookies from your local machine to the server.

1. **Smuggle the Cookie:** Generate `chatgpt_cookies.pkl` on your local machine and securely copy it to a `data/` folder on your server.
2. **Spin up the container:**

```bash
docker-compose up -d --build

```

*Note: The `docker-compose.yml` mounts the `./data` folder into the container, allowing the headless browser to read your locally authenticated session.*

---

## 📡 Usage

Once the API is running, you can stream responses exactly like the official OpenAI API.

### Via cURL

Use the `-N` flag to prevent cURL from buffering the stream:

```bash
curl -N "http://127.0.0.1:8000/api/chat?prompt=Tell+me+a+short+story+about+a+robot"

```

### Via Python Client (`consumer.py`)

This repository includes a `consumer.py` script that connects to the API, handles the SSE stream, and sanitizes OpenAI's hidden metadata markers.

## 🛑 Known Limitations & Troubleshooting

* **Cloudflare Turnstile (IP Bans):** If you deploy this to a cloud provider (AWS, DigitalOcean), Cloudflare may flag the datacenter IP and aggressively serve CAPTCHAs that `playwright-stealth` cannot bypass. Residential proxies are recommended for heavy cloud use.
* **Session Expiry:** Cookies generally last a few weeks to a month. When they expire, the API will return an error. You must regenerate the `chatgpt_cookies.pkl` file locally and replace the old one.
* **Shifted Responses / UI Desync:** If you modify the script to type too quickly, React's internal state may drop the Enter key. The code includes a `1.0s` and `0.5s` `asyncio.sleep()` breather to allow the React UI to catch up. Do not remove these delays!
