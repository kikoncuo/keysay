#!/usr/bin/env python3
"""Generate visual training data for VLM context extraction.

Uses Chrome automation to visit websites, take screenshots, and
send them to Gemini for labeling. Produces training pairs of
(screenshot, extracted_terms) for fine-tuning the VLM.

Usage:
    export OPENROUTER_KEY="sk-or-v1-..."
    python3 scripts/generate_visual_training_data.py \
        --urls urls.txt \
        --output visual_training_data \
        --count 50
"""

import argparse
import base64
import json
import os
import subprocess
import sys
import time

EXTRACT_PROMPT = (
    "Focus on the MAIN CONTENT area of this screenshot (ignore browser tabs, "
    "bookmarks bar, and navigation chrome). Read all text in the main "
    "content: headings, paragraphs, labels, form fields, cards, lists, "
    "sidebar content, and dialog text. "
    "Extract: email addresses, URLs, people names, company names, product "
    "names, medical terms, acronyms, abbreviations, technical jargon, "
    "project names, phone numbers, addresses, and proper nouns. "
    "Include full phrases when they contain specialized vocabulary. "
    "Output ONLY a comma-separated list. Be exhaustive."
)

DEFAULT_URLS = [
    "https://en.wikipedia.org/wiki/Chronic_obstructive_pulmonary_disease",
    "https://en.wikipedia.org/wiki/Machine_learning",
    "https://github.com/trending",
    "https://news.ycombinator.com",
    "https://arxiv.org/list/cs.AI/recent",
    "https://www.who.int/health-topics/chronic-obstructive-pulmonary-disease",
    "https://huggingface.co/models",
    "https://stackoverflow.com/questions",
    "https://www.reuters.com",
    "https://developer.apple.com/documentation",
]


def take_screenshot(output_path: str) -> bool:
    """Take a screenshot of the current screen."""
    try:
        subprocess.run(
            ["screencapture", "-x", "-C", output_path],
            check=True, timeout=10,
        )
        return os.path.exists(output_path)
    except Exception as e:
        print(f"  Screenshot failed: {e}")
        return False


def image_to_base64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def extract_with_gemini(image_path: str, api_key: str) -> list[str]:
    """Send screenshot to Gemini and get extracted terms."""
    b64 = image_to_base64(image_path)

    payload = {
        "model": "google/gemini-3-flash-preview",
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64}"},
                    },
                    {"type": "text", "text": EXTRACT_PROMPT},
                ],
            }
        ],
        "temperature": 0.3,
        "max_tokens": 2000,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "terms",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "terms": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Extracted terms from the screenshot",
                        }
                    },
                    "required": ["terms"],
                    "additionalProperties": False,
                },
            },
        },
    }

    r = subprocess.run(
        [
            "curl", "-s", "https://openrouter.ai/api/v1/chat/completions",
            "-H", "Content-Type: application/json",
            "-H", f"Authorization: Bearer {api_key}",
            "-d", json.dumps(payload),
        ],
        capture_output=True, text=True, timeout=60,
    )

    data = json.loads(r.stdout)
    content = data["choices"][0]["message"]["content"]
    return json.loads(content)["terms"]


def main():
    parser = argparse.ArgumentParser(description="Generate visual training data")
    parser.add_argument("--urls", help="File with URLs (one per line)")
    parser.add_argument("--output", default="visual_training_data", help="Output directory")
    parser.add_argument("--count", type=int, default=50, help="Number of screenshots to process")
    parser.add_argument("--api-key", default=os.environ.get("OPENROUTER_KEY"), help="OpenRouter API key")
    args = parser.parse_args()

    if not args.api_key:
        print("Error: Set OPENROUTER_KEY env var or pass --api-key")
        sys.exit(1)

    # Load URLs
    if args.urls and os.path.exists(args.urls):
        with open(args.urls) as f:
            urls = [line.strip() for line in f if line.strip()]
    else:
        urls = DEFAULT_URLS

    os.makedirs(args.output, exist_ok=True)
    os.makedirs(f"{args.output}/screenshots", exist_ok=True)

    dataset = []
    for i in range(min(args.count, len(urls))):
        url = urls[i % len(urls)]
        print(f"\n[{i+1}/{args.count}] {url}")

        # Open URL in browser (user should have Chrome open)
        subprocess.run(["open", url], timeout=5)
        time.sleep(3)  # Wait for page to load

        # Take screenshot
        img_path = f"{args.output}/screenshots/{i:04d}.png"
        if not take_screenshot(img_path):
            continue

        # Extract terms with Gemini
        try:
            terms = extract_with_gemini(img_path, args.api_key)
            print(f"  Extracted {len(terms)} terms: {terms[:5]}...")

            dataset.append({
                "screenshot": f"screenshots/{i:04d}.png",
                "url": url,
                "terms": terms,
                "terms_csv": ", ".join(terms),
            })
        except Exception as e:
            print(f"  Gemini error: {e}")

    # Save dataset
    with open(f"{args.output}/dataset.json", "w") as f:
        json.dump(dataset, f, indent=2, ensure_ascii=False)

    print(f"\nSaved {len(dataset)} examples to {args.output}/dataset.json")
    print(f"Screenshots in {args.output}/screenshots/")


if __name__ == "__main__":
    main()
