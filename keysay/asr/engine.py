"""ASR engine using mlx-qwen3-asr (Qwen3-ASR on Apple MLX).

Keeps the model session loaded between transcriptions so that only the
first call incurs download / load latency.
"""

import logging
import tempfile
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)


class ASREngine:
    """Wrapper around mlx_qwen3_asr.Session."""

    def __init__(self):
        self._session = None
        self._model_id: str | None = None

    @property
    def is_loaded(self) -> bool:
        return self._session is not None

    def load_model(self, model_id: str = "Qwen/Qwen3-ASR-1.7B"):
        """Load (or reload) the ASR model.

        Args:
            model_id: HuggingFace model identifier. Use pre-quantized repos
                      (e.g. mlx-community/Qwen3-ASR-1.7B-4bit) for smaller models.

        The first call may take a while if the model needs to be downloaded.
        """
        if self._session is not None and self._model_id == model_id:
            logger.debug("Model already loaded: %s", model_id)
            return

        self.unload_model()

        logger.info(
            "Loading ASR model %s — this may take a moment "
            "on first run while the model downloads...",
            model_id,
        )

        from mlx_qwen3_asr import Session

        self._session = Session(model=model_id)
        self._model_id = model_id
        logger.info("ASR model loaded successfully.")

    def transcribe(
        self,
        audio_array: np.ndarray,
        sample_rate: int = 16_000,
        language: str | None = None,
        context: str | None = None,
    ) -> str:
        """Transcribe an audio array to text.

        Args:
            audio_array: float32 numpy array (mono).
            sample_rate: Sample rate of the audio (default 16 kHz).
            language: Language hint (e.g. "English"), or None for auto-detect.
            context: Space-separated context/hint words, or None.

        Returns:
            Transcribed text string.

        Raises:
            RuntimeError: If the model has not been loaded yet.
        """
        if self._session is None:
            raise RuntimeError(
                "ASR model is not loaded. Call load_model() first."
            )

        if audio_array.size == 0:
            logger.warning("Empty audio array — returning empty string.")
            return ""

        import soundfile as sf

        # Write audio to a temporary WAV file for the Session API.
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            sf.write(str(tmp_path), audio_array, sample_rate)

            kwargs: dict = {"language": language} if language else {}
            if context:
                kwargs["context"] = context

            logger.debug(
                "Transcribing %.2f s of audio (lang=%s, context=%s)...",
                len(audio_array) / sample_rate,
                language,
                context,
            )
            result = self._session.transcribe(str(tmp_path), **kwargs)
            text = result.text.strip()
            logger.debug("Transcription result: %r", text)
            return text
        finally:
            tmp_path.unlink(missing_ok=True)

    def unload_model(self):
        """Release the loaded model session and free memory."""
        if self._session is not None:
            logger.info("Unloading ASR model.")
            self._session = None
            self._model_id = None
