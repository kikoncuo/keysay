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
    ("Qwen/Qwen3-ASR-1.7B", "1.7B (Best accuracy, ~5 GB)", 5.0),
    ("Qwen/Qwen3-ASR-0.6B", "0.6B (Lighter, ~2 GB)", 2.0),
]

# VLM models for screen context extraction (Qwen3.5 VLM via mlx-vlm)
VLM_MODELS = [
    ("Enriqueag26/keysay-vlm-context-0.8B-8bit", "0.8B fine-tuned (~3 GB)", 3.0),
    ("mlx-community/Qwen3.5-0.8B-8bit", "0.8B base (~3 GB)", 3.0),
    ("mlx-community/Qwen3.5-2B-4bit", "2B 4-bit (~3 GB)", 3.0),
    ("mlx-community/Qwen3.5-4B-4bit", "4B 4-bit (~5 GB)", 5.0),
    ("mlx-community/Qwen3.5-9B-MLX-4bit", "9B 4-bit (~7 GB)", 7.0),
]

# Estimated RAM for ASR models (derived from SUPPORTED_MODELS)
ASR_RAM_ESTIMATES = {model_id: ram for model_id, _, ram in SUPPORTED_MODELS}

# Estimated RAM for correction model
CORRECTION_RAM_ESTIMATE = 1.5  # 0.8B 8-bit ≈ 1.5 GB


def get_system_ram_gb() -> float:
    """Get total system RAM in GB (macOS)."""
    try:
        import subprocess
        out = subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True)
        return int(out.strip()) / (1024 ** 3)
    except Exception:
        return 0.0

# Preset hotkeys (name, keycode, is_modifier)
HOTKEY_PRESETS = [
    ("Fn / Globe", 63, True),
    ("Right Option", 61, True),
    ("Left Option", 58, True),
    ("Right Command", 54, True),
    ("Left Command", 55, True),
    ("Right Shift", 60, True),
    ("Left Shift", 56, True),
    ("Right Control", 62, True),
    ("Left Control", 59, True),
    ("Caps Lock", 57, True),
]

DEFAULT_HOTKEY_KEYCODE = 61
DEFAULT_HOTKEY_NAME = "Right Option"


@dataclass
class Config:
    active: bool = True
    language: str = "Auto-detect"
    context_words: list[str] = field(default_factory=list)
    replacements: list[list[str]] = field(default_factory=list)  # [[find, replace], ...]
    model_id: str = "Qwen/Qwen3-ASR-1.7B"
    hotkey_keycode: int = DEFAULT_HOTKEY_KEYCODE
    hotkey_name: str = DEFAULT_HOTKEY_NAME
    hotkey_is_modifier: bool = True
    pill_x: int = -1
    pill_y: int = -1
    vlm_enabled: bool = False
    vlm_model: str = "Enriqueag26/keysay-vlm-context-0.8B-8bit"
    correction_model: str = "Enriqueag26/keysay-transcription-cleaner-0.8B-8bit"
    correction_preset: str = "none"
    custom_prompts: dict[str, str] = field(default_factory=dict)  # preset_key → custom system prompt
    mic_device: int = -1  # -1 = system default
    clipboard_fallback: bool = True  # Copy to clipboard instead of Cmd+V when not in text field
    preserve_clipboard: bool = True  # Save and restore clipboard around paste
    dynamic_loading: bool = False  # Load models on demand, unload after each transcription
    developer_mode: bool = False  # Show live system logs in settings

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
            # Migrate old string context_words to list
            cw = data.get("context_words", [])
            if isinstance(cw, str):
                data["context_words"] = cw.split() if cw.strip() else []
            return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
        except (json.JSONDecodeError, TypeError):
            return cls()

    @property
    def language_for_asr(self) -> str | None:
        if self.language == "Auto-detect":
            return None
        return self.language

    @property
    def context_for_asr(self) -> str | None:
        """Space-separated context words for ASR."""
        if not self.context_words:
            return None
        return " ".join(self.context_words)

    def apply_replacements(self, text: str) -> str:
        """Apply find→replace pairs to transcribed text."""
        for pair in self.replacements:
            if len(pair) == 2 and pair[0]:
                text = text.replace(pair[0], pair[1])
        return text
