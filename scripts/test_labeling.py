"""Test: Label an existing image via OpenRouter Gemini Flash."""

import base64
import os
import sys
import requests
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

OPENROUTER_KEY = os.environ["OPENROUTER_KEY"]

EXTRACT_PROMPT = (
    "Focus on the MAIN CONTENT area of the screen (ignore browser tabs, "
    "bookmarks bar, and navigation chrome). Read all text in the main "
    "content: headings, paragraphs, labels, form fields, cards, lists, "
    "sidebar content, and dialog text. "
    "Extract: email addresses, URLs, people names, company names, product "
    "names, medical terms, acronyms, abbreviations, technical jargon, "
    "project names, phone numbers, addresses, and proper nouns. "
    "Include full phrases when they contain specialized vocabulary. "
    "Output ONLY a comma-separated list. Be exhaustive."
)

# Use test_gen.png or first arg
img_path = sys.argv[1] if len(sys.argv) > 1 else str(
    Path(__file__).resolve().parent.parent / "vlm_training" / "images" / "test_gen.png"
)

if not os.path.exists(img_path):
    print(f"Image not found: {img_path}")
    print("Run test_image_gen.py first")
    sys.exit(1)

with open(img_path, "rb") as f:
    img_b64 = base64.b64encode(f.read()).decode()

print(f"Labeling image: {img_path}")
resp = requests.post(
    "https://openrouter.ai/api/v1/chat/completions",
    headers={
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type": "application/json",
    },
    json={
        "model": "google/gemini-3-flash-preview",
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{img_b64}"},
                    },
                    {"type": "text", "text": EXTRACT_PROMPT},
                ],
            }
        ],
        "max_tokens": 1024,
    },
    timeout=120,
)
resp.raise_for_status()
data = resp.json()

msg = data["choices"][0]["message"]
text = msg.get("content", "")
if isinstance(text, list):
    text = " ".join(p.get("text", "") for p in text if isinstance(p, dict) and p.get("type") == "text")

print(f"\nExtracted labels:\n{text}")
