"""Settings persistence for keysay."""

import json
import os
from dataclasses import dataclass, field, asdict


CONFIG_DIR = os.path.expanduser("~/Library/Application Support/keysay")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")

SUPPORTED_LANGUAGES = [
    "Auto-detect",
    "English",
    "Spanish",
    "Chinese",
    "Cantonese",
    "French",
    "German",
    "Italian",
    "Japanese",
    "Korean",
    "Portuguese",
    "Russian",
]

SUPPORTED_MODELS = [
    ("Qwen/Qwen3-ASR-1.7B", "1.7B (Best accuracy)"),
    ("Qwen/Qwen3-ASR-0.6B", "0.6B (Faster)"),
]

SUPPORTED_QUANTIZATIONS = [
    ("", "Full precision (bf16)"),
    ("q8", "8-bit (fast, near-lossless)"),
    ("q4", "4-bit (fastest)"),
]

# Default hotkey: Right Option (keycode 0x3D = 61)
DEFAULT_HOTKEY_KEYCODE = 61
DEFAULT_HOTKEY_NAME = "Right Option"


@dataclass
class Config:
    active: bool = True
    language: str = "Auto-detect"
    context_words: str = ""
    model_id: str = "Qwen/Qwen3-ASR-1.7B"
    quantization: str = ""
    hotkey_keycode: int = DEFAULT_HOTKEY_KEYCODE
    hotkey_name: str = DEFAULT_HOTKEY_NAME
    hotkey_is_modifier: bool = True
    pill_x: int = -1  # -1 = auto-center
    pill_y: int = -1

    def save(self):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(CONFIG_PATH, "w") as f:
            json.dump(asdict(self), f, indent=2)

    @classmethod
    def load(cls) -> "Config":
        if not os.path.exists(CONFIG_PATH):
            return cls()
        try:
            with open(CONFIG_PATH) as f:
                data = json.load(f)
            return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
        except (json.JSONDecodeError, TypeError):
            return cls()

    @property
    def language_for_asr(self) -> str | None:
        """Return language string for ASR, or None for auto-detect."""
        if self.language == "Auto-detect":
            return None
        return self.language

    @property
    def context_for_asr(self) -> str | None:
        """Return context string for ASR, or None if empty."""
        text = self.context_words.strip()
        return text if text else None

    @property
    def quantization_for_asr(self) -> str | None:
        """Return quantization string for ASR, or None for full precision."""
        return self.quantization if self.quantization else None
