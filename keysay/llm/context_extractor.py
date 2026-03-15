"""VLM-based screen context extractor for keysay.

Takes a screenshot, feeds it to a Qwen3.5 VLM, and extracts proper nouns,
brand names, and technical terms to pass as ASR context hints.
"""

import logging
import os

from keysay.llm._patches import apply_transformers_patches

apply_transformers_patches()

logger = logging.getLogger(__name__)

_EXTRACT_PROMPT = (
    "You are extracting speech recognition context hints from a screenshot. "
    "These hints help an ASR model recognize uncommon words it might otherwise mishear. "
    "EXTRACT ONLY terms that are clearly legible: people names, company/brand names, "
    "product names, project/repository names, email addresses, URLs, domain-specific jargon, "
    "technical terms, acronyms, specialized vocabulary, and proper nouns. "
    "EXCLUDE: application menus and toolbars (File, Edit, View, Insertar, etc.), "
    "generic UI labels (Inbox, Sent, Drafts, Compose, Search), window controls, "
    "common everyday words, dates, timestamps, and pure numbers. "
    "SKIP any text that appears blurry, garbled, or not clearly readable. "
    "Output ONLY a comma-separated list. No explanations or categories."
)


class ContextExtractor:
    """Loads a VLM and extracts context words from screenshots."""

    def __init__(self):
        self._model = None
        self._processor = None
        self._model_id: str | None = None

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    def load_model(self, model_id: str) -> None:
        if self._model is not None and self._model_id == model_id:
            logger.debug("VLM already loaded: %s", model_id)
            return

        self.unload_model()

        logger.info("Loading VLM %s ...", model_id)
        from mlx_vlm import load

        self._model, self._processor = load(model_id)
        self._model_id = model_id
        logger.info("VLM loaded: %s", model_id)

    def unload_model(self) -> None:
        if self._model is not None:
            logger.info("Unloading VLM.")
            self._model = None
            self._processor = None
            self._model_id = None

    def extract_context(self, screenshot_path: str, max_tokens: int = 500) -> list[str]:
        """Extract context words from a screenshot.

        Args:
            screenshot_path: Path to a PNG screenshot.
            max_tokens: Max tokens for VLM generation.

        Returns:
            List of extracted context words/phrases.
        """
        if self._model is None or self._processor is None:
            raise RuntimeError("VLM not loaded.")

        from mlx_vlm import generate
        from mlx_vlm.prompt_utils import apply_chat_template

        prompt = apply_chat_template(
            self._processor,
            config=self._model.config,
            prompt=_EXTRACT_PROMPT,
            num_images=1,
        )

        result = generate(
            self._model,
            self._processor,
            prompt=prompt,
            image=screenshot_path,
            max_tokens=max_tokens,
            verbose=False,
        )

        # result is a GenerationResult with .text attribute
        raw = result.text if hasattr(result, "text") else str(result)
        return _parse_context_words(raw)

    def correct(
        self,
        raw_text: str,
        system_prompt: str,
        max_tokens: int = 2048,
    ) -> str:
        """Correct/reformat transcribed text using the VLM in text-only mode.

        Args:
            raw_text: Raw transcription from ASR.
            system_prompt: The preset system prompt.
            max_tokens: Maximum tokens to generate.

        Returns:
            Corrected text string.
        """
        if self._model is None or self._processor is None:
            raise RuntimeError("VLM not loaded.")

        from mlx_vlm import generate
        from mlx_vlm.prompt_utils import apply_chat_template

        user_content = f"Transcription: {raw_text}"
        prompt = apply_chat_template(
            self._processor,
            config=self._model.config,
            prompt=f"{system_prompt}\n\n{user_content}",
            num_images=0,
        )

        result = generate(
            self._model,
            self._processor,
            prompt=prompt,
            max_tokens=max_tokens,
            verbose=False,
            temp=1.0,
            top_p=0.95,
            repetition_penalty=1.05,
        )

        raw = result.text if hasattr(result, "text") else str(result)

        # Strip thinking tags if present
        import re
        match = re.search(r"</think>\s*(.*)", raw, re.DOTALL)
        text = match.group(1).strip() if match else raw.strip()
        return text


_STOP_WORDS = frozenset({
    "a", "an", "the", "in", "on", "at", "to", "for", "of", "and", "or",
    "is", "it", "was", "be", "are", "not", "no", "can", "will", "do",
    "if", "but", "with", "from", "by", "as", "that", "this", "all",
    "only", "also", "than", "each", "has", "had", "have", "been", "were",
    "won't", "don't", "its", "he", "she", "we", "you", "they", "me",
    "my", "your", "his", "her", "our", "up", "so", "out", "just",
})


def _parse_context_words(raw: str) -> list[str]:
    """Parse VLM output into a deduplicated, filtered word list."""
    words = []
    seen = set()
    for part in raw.replace("\n", ",").split(","):
        word = part.strip().strip(".-\"'()[]{}")
        if not word or len(word) < 2:
            continue
        key = word.lower()
        if key in seen or key in _STOP_WORDS:
            continue
        # Skip pure numbers and timestamps
        if word.replace(":", "").replace(".", "").replace("-", "").isdigit():
            continue
        seen.add(key)
        words.append(word)
    return words
