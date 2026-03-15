"""Text correction using a fine-tuned model via mlx_lm.

Uses the fused keysay-transcription-cleaner model to clean speech
transcriptions: removes self-corrections, filler words, etc.
"""

import logging
import re

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You clean speech-to-text transcriptions into ready-to-send chat messages.\n\n"
    "Remove self-corrections (keep only the final version). Remove filler words.\n"
    "Never rephrase. Never add words. Keep the original language."
)


class Corrector:
    """Loads the fine-tuned correction model and cleans transcriptions."""

    def __init__(self):
        self._model = None
        self._tokenizer = None
        self._model_id: str | None = None

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    def load_model(self, model_id: str) -> None:
        if self._model is not None and self._model_id == model_id:
            return

        self.unload_model()

        logger.info("Loading correction model %s ...", model_id)
        from mlx_lm import load

        self._model, self._tokenizer = load(model_id)
        self._model_id = model_id
        logger.info("Correction model loaded: %s", model_id)

    def unload_model(self) -> None:
        if self._model is not None:
            logger.info("Unloading correction model.")
            self._model = None
            self._tokenizer = None
            self._model_id = None

    def correct(self, raw_text: str, system_prompt: str | None = None, max_tokens: int = 1024) -> str:
        """Clean a transcription.

        Args:
            raw_text: Raw transcription from ASR.
            system_prompt: Override system prompt (uses default if None).
            max_tokens: Max generation tokens.

        Returns:
            Cleaned text.
        """
        if self._model is None or self._tokenizer is None:
            raise RuntimeError("Correction model not loaded.")

        from mlx_lm import generate

        system = system_prompt or _SYSTEM_PROMPT
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": raw_text},
        ]
        prompt = self._tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True,
            enable_thinking=False,
        )

        result = generate(self._model, self._tokenizer, prompt=prompt, max_tokens=max_tokens)

        # Strip thinking tags if present
        match = re.search(r"</think>\s*(.*)", result, re.DOTALL)
        return match.group(1).strip() if match else result.strip()
