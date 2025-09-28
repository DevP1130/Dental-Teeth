#!/usr/bin/env python3
"""
check_openai_key.py

Quick script to verify that OPENAI_API_KEY (from environment or .env) is valid.
Run with the project's venv to use the same environment:
    .\.venv\Scripts\python.exe check_openai_key.py

Exit codes:
 0 = key valid (or rate limited but valid)
 1 = unauthorized / invalid key
 2 = OPENAI_API_KEY not set
 3 = network/connection error
 4 = failed to parse JSON response
 5 = other unexpected response
"""

import os
import sys
import requests
from dotenv import load_dotenv

load_dotenv()

KEY = os.environ.get('OPENAI_API_KEY')
if not KEY:
    print("OPENAI_API_KEY not found in environment or .env")
    sys.exit(2)

MODEL = os.environ.get('OPENAI_API_MODEL', 'gpt-5-mini')

payload = {
    "model": MODEL,
    "messages": [{"role": "user", "content": "Please reply with the single word OK."}],
    "max_tokens": 5,
    "temperature": 0,
}

headers = {
    "Authorization": f"Bearer {KEY}",
    "Content-Type": "application/json",
}

try:
    resp = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=15)
except Exception as e:
    print("Network error while contacting OpenAI:", e)
    sys.exit(3)

print("HTTP status:", resp.status_code)

if resp.status_code == 200:
    try:
        j = resp.json()
        # Try to extract assistant text
        assistant = None
        try:
            assistant = j['choices'][0]['message']['content']
        except Exception:
            assistant = None
        print("Key appears valid.")
        if assistant:
            print("Assistant response:\n", assistant.strip())
        else:
            print("No assistant content returned; raw response:\n", resp.text)
        sys.exit(0)
    except Exception as e:
        print("Failed to parse JSON response:", e)
        print(resp.text)
        sys.exit(4)
elif resp.status_code == 401:
    print("Unauthorized (401). Key is invalid or revoked.")
    print(resp.text)
    sys.exit(1)
elif resp.status_code == 429:
    print("Rate limited (429). Key is valid but quota/rate limited.")
    print(resp.text)
    sys.exit(0)
else:
    print("Unexpected response (status {}):".format(resp.status_code))
    print(resp.text)
    sys.exit(5)
