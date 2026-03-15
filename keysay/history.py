"""Transcription history persistence."""

import json
import os
from datetime import datetime

CONFIG_DIR = os.path.expanduser("~/Library/Application Support/keysay")
HISTORY_PATH = os.path.join(CONFIG_DIR, "history.json")
MAX_ENTRIES = 200


def load_history() -> list[dict]:
    if not os.path.exists(HISTORY_PATH):
        return []
    try:
        with open(HISTORY_PATH) as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def save_history(entries: list[dict]) -> None:
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(HISTORY_PATH, "w") as f:
        json.dump(entries[-MAX_ENTRIES:], f, indent=2)


def add_entry(text: str, duration_s: float, model: str, raw_text: str = "") -> None:
    entries = load_history()
    entries.append({
        "timestamp": datetime.now().isoformat(),
        "text": text,
        "raw_text": raw_text,
        "duration_s": round(duration_s, 1),
        "model": model,
    })
    save_history(entries)


def clear_history() -> None:
    save_history([])
