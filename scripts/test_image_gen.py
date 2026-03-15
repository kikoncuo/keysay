"""Test: Generate a single image via OpenRouter Gemini image preview."""

import base64
import os
import requests
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

OPENROUTER_KEY = os.environ["OPENROUTER_KEY"]

prompt = "Create an image of a Gmail inbox showing a corporate email about a medical report. Format: Mac screenshot, only screen, realistic"

print(f"Generating image...")
resp = requests.post(
    "https://openrouter.ai/api/v1/chat/completions",
    headers={
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type": "application/json",
    },
    json={
        "model": "google/gemini-3.1-flash-image-preview",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 4096,
    },
    timeout=120,
)
resp.raise_for_status()
data = resp.json()

msg = data["choices"][0]["message"]
print(f"Message keys: {list(msg.keys())}")

# Images come in msg["images"] field
images = msg.get("images", [])
content = msg.get("content")

img_bytes = None

# Check "images" field first (OpenRouter native image output)
if images:
    img_data = images[0]
    if isinstance(img_data, dict) and "image_url" in img_data:
        url = img_data["image_url"]["url"]
        if url.startswith("data:image"):
            b64 = url.split(",", 1)[1]
            img_bytes = base64.b64decode(b64)
    elif isinstance(img_data, str):
        img_bytes = base64.b64decode(img_data)

# Fallback: check content for inline images
if img_bytes is None and isinstance(content, list):
    for part in content:
        if isinstance(part, dict):
            if part.get("type") == "image_url":
                url = part["image_url"]["url"]
                if url.startswith("data:image"):
                    b64 = url.split(",", 1)[1]
                    img_bytes = base64.b64decode(b64)
                    break

if img_bytes:
    out = Path(__file__).resolve().parent.parent / "vlm_training" / "images" / "test_gen.png"
    out.write_bytes(img_bytes)
    print(f"Saved: {out} ({len(img_bytes)} bytes)")
    os.system(f"open {out}")
else:
    print("No image found in response!")
    print(f"Content: {repr(content)[:300]}")
    print(f"Images: {repr(images)[:300]}")
