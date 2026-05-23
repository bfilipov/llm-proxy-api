# Qwen Chat API

A FastAPI‑based service that automates [Qwen Chat](https://chat.qwen.ai/) using Playwright.  
Send a message to the endpoint and receive the full assistant response – all session handling, login, and cookie persistence are managed automatically.

## Features

- 🔐 **Automatic login** – reads credentials from `.env` and saves cookies for future runs.
- 🍪 **Cookie persistence** – reuse the same session across server restarts.
- 🧠 **Wait for complete responses** – detects when the assistant has stopped typing / thinking.
- 🚀 **Production‑ready** – runs Playwright in the background, handles requests sequentially (lock) to avoid context clashes.
- 🐍 **Sync Playwright inside FastAPI** – uses a thread pool to keep the event loop free.

## Prerequisites

- Python 3.8+
- Playwright browsers (install with `playwright install chromium`)

## Installation

```bash
# Install dependencies
poetry install

# Install the Playwright Chromium browser
playwright install chromium

## Configuration
Create a .env file in the project root:

```
QWEN_EMAIL=your_email@example.com
QWEN_PASSWORD=your_password
```

## Running the Server

```uvicorn main:app --reload --host 0.0.0.0 --port 8000```

The browser starts once at server startup.

On first run, the service will log in automatically and save cookies to .qwen_cookies.json.

Subsequent runs (including after a restart) reuse the saved session until it expires.
