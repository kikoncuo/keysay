"""Real-time microphone capture using sounddevice.

Records 16 kHz mono float32 audio and provides per-block RMS levels
for driving a waveform UI.
"""

import logging

import numpy as np

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16_000
CHANNELS = 1
DTYPE = "float32"
BLOCKSIZE = 1024  # ~64 ms at 16 kHz


class MicrophoneNotFoundError(Exception):
    """Raised when no input device is available."""


def list_input_devices() -> list[tuple[int, str, bool]]:
    """Return available input devices as [(index, name, is_default), ...]."""
    import sounddevice as sd
    devices = sd.query_devices()
    default_input = sd.default.device[0]
    result = []
    for i, dev in enumerate(devices):
        if dev["max_input_channels"] > 0:
            is_default = (i == default_input)
            result.append((i, dev["name"], is_default))
    return result


class Recorder:
    """Accumulates microphone audio while recording."""

    def __init__(self, rms_callback=None):
        """
        Args:
            rms_callback: Optional callable(float) invoked with the RMS level
                (0.0 - 1.0) of each audio block. Called from the audio thread.
        """
        self.rms_callback = rms_callback
        self._stream = None
        self._chunks: list[np.ndarray] = []
        self._recording = False

    def start(self, device=None):
        """Begin recording from the specified or default microphone.

        Args:
            device: sounddevice device index, or None for system default.

        Raises MicrophoneNotFoundError if no input device is found.
        """
        import sounddevice as sd

        try:
            if device is not None:
                dev_info = sd.query_devices(device)
            else:
                dev_info = sd.query_devices(kind="input")
            if dev_info is None:
                raise MicrophoneNotFoundError("No input audio device found.")
        except (sd.PortAudioError, ValueError) as exc:
            raise MicrophoneNotFoundError(
                f"Could not query audio devices: {exc}"
            ) from exc

        self._chunks = []
        self._recording = True

        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype=DTYPE,
            blocksize=BLOCKSIZE,
            device=device,
            callback=self._audio_callback,
        )
        self._stream.start()
        logger.debug("Recording started (16 kHz, mono, float32, device=%s).", device)

    def stop(self) -> np.ndarray:
        """Stop recording and return the accumulated audio.

        Returns:
            numpy float32 array of shape (num_samples,) at 16 kHz.
            Returns an empty array if nothing was recorded.
        """
        self._recording = False

        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

        if not self._chunks:
            logger.warning("No audio chunks captured.")
            return np.array([], dtype=np.float32)

        audio = np.concatenate(self._chunks, axis=0).squeeze()
        self._chunks = []
        logger.debug("Recording stopped. Captured %d samples (%.2f s).",
                      len(audio), len(audio) / SAMPLE_RATE)
        return audio

    def _audio_callback(self, indata, frames, time_info, status):
        """sounddevice InputStream callback — runs in the audio thread."""
        if status:
            logger.warning("Audio callback status: %s", status)

        if not self._recording:
            return

        # list.append is GIL-atomic, so this is thread-safe.
        self._chunks.append(indata.copy())

        if self.rms_callback is not None:
            rms = float(np.sqrt(np.mean(indata ** 2)))
            # Gentler scaling: pow(rms * 80, 0.6) gives a smoother ramp
            # 0.0002→0.03, 0.001→0.10, 0.005→0.30, 0.02→0.65, 0.05→1.0
            scaled = min(float((rms * 80.0) ** 0.6), 1.0)
            self.rms_callback(scaled)
