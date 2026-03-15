"""Main application: single poll timer drives everything on the main thread."""

import logging
import os
import sys
import threading

from PyQt6.QtCore import QObject, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import QApplication

from keysay.config import Config

logger = logging.getLogger(__name__)


class KeysayApp(QObject):
    """Central orchestrator — one poll timer, no cross-thread signals for hotkey."""

    _sig_model_loaded = pyqtSignal()
    _sig_model_error = pyqtSignal(str)
    _sig_transcription_done = pyqtSignal(str)
    _sig_transcription_error = pyqtSignal(str)
    _sig_vlm_loaded = pyqtSignal()
    _sig_vlm_error = pyqtSignal(str)
    _sig_corrector_loaded = pyqtSignal()
    _sig_corrector_error = pyqtSignal(str)
    _sig_download_started = pyqtSignal(str)
    _sig_history_updated = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._app = QApplication(sys.argv)
        self._app.setQuitOnLastWindowClosed(False)

        # Set app icon (Qt windows + macOS dock)
        from PyQt6.QtGui import QIcon
        icon_path = os.path.join(os.path.dirname(__file__), "ui", "icon.png")
        if os.path.exists(icon_path):
            self._app.setWindowIcon(QIcon(icon_path))
            try:
                from AppKit import NSApplication, NSImage
                ns_icon = NSImage.alloc().initWithContentsOfFile_(icon_path)
                if ns_icon:
                    NSApplication.sharedApplication().setApplicationIconImage_(ns_icon)
            except Exception:
                pass

        self._config = Config.load()

        # Backend
        from keysay.asr.engine import ASREngine
        from keysay.audio.recorder import Recorder
        from keysay.hotkey.cgevent_listener import HotkeyListener

        self._latest_rms: float = 0.0
        self._engine = ASREngine()
        self._recorder = Recorder(rms_callback=self._on_rms)
        self._listener = HotkeyListener(
            keycode=self._config.hotkey_keycode,
            is_modifier=self._config.hotkey_is_modifier,
        )

        self._recording = False
        self._transcribing = False
        self._model_ready = False
        self._was_pressed = False
        self._last_duration: float = 0.0
        self._last_raw_text: str = ""
        self._target_app = None  # NSRunningApplication captured at hotkey press

        # VLM context extraction
        from keysay.llm.context_extractor import ContextExtractor
        self._extractor = ContextExtractor()
        self._vlm_ready = False
        self._vlm_context_words: list[str] = []
        self._vlm_done = threading.Event()
        self._vlm_done.set()  # initially "done" (nothing pending)
        self._screenshot_path: str | None = None

        # Correction model (fine-tuned, separate from VLM)
        from keysay.llm.corrector import Corrector
        self._corrector = Corrector()
        self._corrector_ready = False

        # GPU lock — prevent concurrent MLX operations (Metal crashes)
        self._gpu_lock = threading.Lock()

        # UI
        from keysay.ui.pill import FloatingPill
        from keysay.ui.tray import TrayIcon

        self._pill = FloatingPill()
        self._tray = TrayIcon(active=self._config.active)

        # Single poll timer: hotkey transitions + RMS forwarding (60fps)
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(16)
        self._poll_timer.timeout.connect(self._poll_tick)

        # Signals for background → main thread
        self._sig_model_loaded.connect(self._on_model_loaded)
        self._sig_model_error.connect(self._on_model_error)
        self._sig_transcription_done.connect(self._on_transcription_done)
        self._sig_transcription_error.connect(self._on_transcription_error)
        self._sig_vlm_loaded.connect(self._on_vlm_loaded)
        self._sig_vlm_error.connect(self._on_vlm_error)
        self._sig_corrector_loaded.connect(self._on_corrector_loaded)
        self._sig_corrector_error.connect(self._on_corrector_error)
        self._sig_download_started.connect(self._on_download_started)

        # UI signals
        self._tray.open_settings.connect(self._show_settings)
        self._tray.toggle_active.connect(self._set_active)
        self._tray.quit_app.connect(self._quit)
        self._pill.settings_requested.connect(self._show_settings)

    def _dbg(self, msg: str):
        """Write directly to a debug log file (bypasses logging framework)."""
        import os, time
        path = os.path.expanduser("~/Library/Application Support/keysay/debug.log")
        with open(path, "a") as f:
            f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")
            f.flush()

    def run(self) -> int:
        self._dbg("=== keysay starting ===")
        from keysay.ui.permissions_dialog import check_and_prompt
        if not check_and_prompt():
            return 0

        self._dbg(f"active={self._config.active}, dynamic={self._config.dynamic_loading}")
        if self._config.active:
            self._pill.restore_position(self._config.pill_x, self._config.pill_y)
            self._pill.show()
            self._listener.start()
            self._dbg("listener started")
            self._poll_timer.start()

            if self._config.dynamic_loading:
                # Don't preload — models load on first hotkey press
                self._pill.set_state("idle")
                self._dbg("dynamic loading — models will load on first press")
            else:
                self._pill.set_state("loading")
                self._dbg("starting model load threads")
                self._load_model_async()
                if self._config.vlm_enabled or self._config.correction_preset != "none":
                    self._load_vlm_and_corrector_async()
                self._dbg("model load threads started")

        self._tray.show()

        logger.info("keysay running. Hotkey: %s", self._config.hotkey_name)
        return self._app.exec()

    # ------------------------------------------------------------------
    # Poll tick — runs on main thread at 60fps
    # ------------------------------------------------------------------

    @pyqtSlot()
    def _poll_tick(self):
        pressed = self._listener.pressed

        # Detect transitions
        if pressed and not self._was_pressed:
            self._handle_press()
        elif not pressed and self._was_pressed:
            self._handle_release()
        self._was_pressed = pressed

        # Forward RMS to waveform while recording
        if self._recording:
            self._pill.update_waveform(self._latest_rms)

    # ------------------------------------------------------------------
    # RMS callback (audio thread — just store, no Qt calls)
    # ------------------------------------------------------------------

    def _on_rms(self, level: float):
        self._latest_rms = level

    # ------------------------------------------------------------------
    # ASR model loading
    # ------------------------------------------------------------------

    def _load_model_async(self):
        self._model_ready = False
        if self._pill.isVisible() and not self._recording:
            self._pill.set_state("loading")

        model_id = self._config.model_id
        quantization = self._config.quantization_for_asr

        def _load():
            try:
                self._dbg("ASR load thread started")
                from keysay.models import is_model_cached
                if not is_model_cached(model_id):
                    self._sig_download_started.emit(model_id)
                self._engine.load_model(model_id, quantization)
                self._dbg("ASR model loaded OK")
                self._sig_model_loaded.emit()
            except Exception as exc:
                self._dbg(f"ASR load FAILED: {exc}")
                logger.error("Failed to load ASR model: %s", exc, exc_info=True)
                self._sig_model_error.emit(str(exc))

        threading.Thread(target=_load, daemon=True).start()

    @pyqtSlot()
    def _on_model_loaded(self):
        self._model_ready = True
        logger.info("ASR model ready.")
        if self._recording:
            # Don't change pill state — stay in "recording"
            return
        if self._pill.isVisible() and self._pill._state in ("loading", "not_ready"):
            self._pill.set_state("idle")

    @pyqtSlot(str)
    def _on_model_error(self, msg: str):
        self._model_ready = False
        logger.error("ASR model load failed: %s", msg)

    # ------------------------------------------------------------------
    # VLM loading
    # ------------------------------------------------------------------

    def _load_vlm_and_corrector_async(self):
        """Load VLM and corrector sequentially in one thread to avoid import deadlock."""
        self._vlm_ready = False
        self._corrector_ready = False

        def _load_both():
            from keysay.models import is_model_cached

            if self._config.vlm_enabled:
                try:
                    if not is_model_cached(self._config.vlm_model):
                        self._sig_download_started.emit(self._config.vlm_model)
                    self._extractor.load_model(self._config.vlm_model)
                    self._sig_vlm_loaded.emit()
                except Exception as exc:
                    logger.error("Failed to load VLM: %s", exc)
                    self._sig_vlm_error.emit(str(exc))

            if self._config.correction_preset != "none":
                try:
                    if not is_model_cached(self._config.correction_model):
                        self._sig_download_started.emit(self._config.correction_model)
                    self._corrector.load_model(self._config.correction_model)
                    self._sig_corrector_loaded.emit()
                except Exception as exc:
                    logger.error("Failed to load corrector: %s", exc)
                    self._sig_corrector_error.emit(str(exc))

        threading.Thread(target=_load_both, daemon=True).start()

    def _load_vlm_async(self):
        self._vlm_ready = False
        vlm_model = self._config.vlm_model

        def _load():
            try:
                from keysay.models import is_model_cached
                if not is_model_cached(vlm_model):
                    self._sig_download_started.emit(vlm_model)
                self._extractor.load_model(vlm_model)
                self._sig_vlm_loaded.emit()
            except Exception as exc:
                logger.error("Failed to load VLM: %s", exc)
                self._sig_vlm_error.emit(str(exc))

        threading.Thread(target=_load, daemon=True).start()

    @pyqtSlot()
    def _on_vlm_loaded(self):
        self._vlm_ready = True
        logger.info("VLM ready.")

    @pyqtSlot(str)
    def _on_vlm_error(self, msg: str):
        self._vlm_ready = False
        logger.error("VLM load failed: %s", msg)

    # ------------------------------------------------------------------
    # Corrector loading
    # ------------------------------------------------------------------

    def _load_corrector_async(self):
        self._corrector_ready = False
        correction_model = self._config.correction_model

        def _load():
            try:
                from keysay.models import is_model_cached
                if not is_model_cached(correction_model):
                    self._sig_download_started.emit(correction_model)
                self._corrector.load_model(correction_model)
                self._sig_corrector_loaded.emit()
            except Exception as exc:
                logger.error("Failed to load corrector: %s", exc)
                self._sig_corrector_error.emit(str(exc))

        threading.Thread(target=_load, daemon=True).start()

    @pyqtSlot()
    def _on_corrector_loaded(self):
        self._corrector_ready = True
        logger.info("Corrector ready.")

    @pyqtSlot(str)
    def _on_corrector_error(self, msg: str):
        self._corrector_ready = False
        logger.error("Corrector load failed: %s", msg)

    # ------------------------------------------------------------------
    # Press / Release handlers (main thread, no races)
    # ------------------------------------------------------------------

    def _handle_press(self):
        self._dbg(f"PRESS: recording={self._recording}, model_ready={self._model_ready}, dynamic={self._config.dynamic_loading}")
        if self._recording:
            return

        # Capture the frontmost app BEFORE we do anything — this is where
        # the transcribed text will be pasted after recording.
        try:
            from AppKit import NSWorkspace
            self._target_app = NSWorkspace.sharedWorkspace().frontmostApplication()
            self._dbg(f"Target app: {self._target_app.localizedName()} (pid={self._target_app.processIdentifier()})")
        except Exception:
            self._target_app = None

        if not self._model_ready and not self._config.dynamic_loading:
            self._pill.set_state("not_ready")
            return

        # If VLM is enabled and ready, take screenshot + start extraction in parallel
        if self._config.vlm_enabled and self._vlm_ready:
            try:
                from keysay.screenshot import capture_screen
                self._screenshot_path = capture_screen()
                self._vlm_done = threading.Event()
                threading.Thread(
                    target=self._extract_context,
                    args=(self._screenshot_path,),
                    daemon=True,
                ).start()
            except Exception as exc:
                logger.error("Screenshot failed: %s", exc)
                self._vlm_done.set()
        else:
            self._vlm_done.set()

        self._recording = True  # flag set early to prevent re-entry

        if self._config.dynamic_loading and not self._model_ready:
            # Dynamic loading: show loading indicator, start models, delay recording 300ms
            self._pill.set_state("loading")
            self._load_model_async()
            if self._config.vlm_enabled or self._config.correction_preset != "none":
                self._load_vlm_and_corrector_async()
            QTimer.singleShot(300, self._start_recording)
        else:
            # Models already loaded — start recording immediately
            self._start_recording()

    def _start_recording(self):
        """Actually start the audio stream."""
        if not self._recording:
            return
        self._latest_rms = 0.0
        try:
            mic = self._config.mic_device if self._config.mic_device >= 0 else None
            self._recorder.start(device=mic)
            self._pill.set_state("recording")
        except Exception as exc:
            logger.error("Failed to start recording: %s", exc)
            self._recording = False
            self._pill.set_state("idle")

    def _extract_context(self, screenshot_path: str):
        """Run VLM context extraction in background (parallel with recording)."""
        try:
            with self._gpu_lock:
                words = self._extractor.extract_context(screenshot_path)
            self._vlm_context_words = words
            logger.info("VLM context: %s", words)
        except Exception as exc:
            logger.error("VLM extraction error: %s", exc)
            self._vlm_context_words = []
        finally:
            self._vlm_done.set()
            # Clean up screenshot
            try:
                os.unlink(screenshot_path)
            except OSError:
                pass

    def _handle_release(self):
        self._dbg(f"RELEASE: recording={self._recording}")
        if not self._recording:
            return
        # Keep recording for 500ms after key release to capture trailing speech
        QTimer.singleShot(500, self._finish_recording)

    def _finish_recording(self):
        self._dbg(f"FINISH_RECORDING: recording={self._recording}")
        if not self._recording:
            return
        self._recording = False

        try:
            audio = self._recorder.stop()
        except Exception as exc:
            logger.error("Failed to stop recording: %s", exc)
            self._pill.set_state("idle")
            return

        if audio.size == 0:
            self._pill.set_state("idle")
            return

        duration = audio.size / 16_000
        self._last_duration = duration
        logger.info("Recorded %.1fs of audio.", duration)

        if self._transcribing:
            logger.warning("ASR busy — dropping recording.")
            self._pill.set_state("idle")
            return

        self._transcribing = True
        self._pill.set_state("processing")

        language = self._config.language_for_asr
        manual_context = self._config.context_for_asr
        vlm_done_event = self._vlm_done
        correction_preset = self._config.correction_preset
        vlm_ready = self._vlm_ready

        dynamic = self._config.dynamic_loading

        def _transcribe_and_paste():
            try:
                self._dbg("TRANSCRIBE thread started")
                # Wait for model to load if dynamic loading
                if dynamic:
                    for _ in range(300):  # up to 30s
                        if self._model_ready:
                            break
                        import time
                        time.sleep(0.1)

                # Wait for VLM context extraction if it's still running
                vlm_done_event.wait(timeout=15)

                # Merge manual + VLM context words
                all_context_parts = []
                if manual_context:
                    all_context_parts.append(manual_context)
                if self._vlm_context_words:
                    all_context_parts.append(" ".join(self._vlm_context_words))
                context = " ".join(all_context_parts) if all_context_parts else None

                self._dbg(f"TRANSCRIBE: waiting for GPU lock (vlm_done={vlm_done_event.is_set()})")
                with self._gpu_lock:
                    self._dbg("TRANSCRIBE: got GPU lock, transcribing...")
                    text = self._engine.transcribe(
                        audio, language=language, context=context,
                    )
                self._dbg(f"TRANSCRIBE result: '{text[:80] if text else '(empty)'}...'")
                if text.strip():
                    self._last_raw_text = text
                    text = self._config.apply_replacements(text)

                    # Post-processing correction if preset selected
                    if (correction_preset != "none"
                            and self._corrector_ready
                            and self._corrector.is_loaded):
                        from keysay.llm.presets import CORRECTION_PRESETS
                        preset = CORRECTION_PRESETS.get(correction_preset)
                        if preset:
                            system_prompt = self._config.custom_prompts.get(
                                correction_preset, preset["system"]
                            )
                            logger.info("Correcting with preset: %s", correction_preset)
                            with self._gpu_lock:
                                text = self._corrector.correct(text, system_prompt)
                            logger.info("Corrected: %s", text)

                self._dbg(f"TRANSCRIBE: emitting done signal, text='{text[:80] if text else ''}'")
                self._sig_transcription_done.emit(text)
            except Exception as exc:
                self._dbg(f"TRANSCRIBE FAILED: {exc}")
                self._sig_transcription_error.emit(str(exc))

        threading.Thread(target=_transcribe_and_paste, daemon=True).start()

    # ------------------------------------------------------------------
    # Transcription results (main thread via signals)
    # ------------------------------------------------------------------

    @pyqtSlot(str)
    def _on_download_started(self, model_id: str):
        logger.info("Downloading model: %s", model_id)
        self._pill.set_loading_text("Downloading...")

    @pyqtSlot(str)
    def _on_transcription_done(self, text: str):
        self._transcribing = False

        if text.strip():
            logger.info("Transcribed: %s", text)

            # Record to history
            try:
                from keysay.history import add_entry
                add_entry(
                    text=text,
                    duration_s=self._last_duration,
                    model=self._config.model_id,
                    raw_text=self._last_raw_text if self._last_raw_text != text else "",
                )
                self._sig_history_updated.emit()
            except Exception as exc:
                logger.debug("Failed to save history: %s", exc)

            from keysay.paste.paster import paste_text
            target_name = self._target_app.localizedName() if self._target_app else "none"
            self._dbg(f"PASTE: target={target_name}, text='{text[:40]}'")
            status = paste_text(
                text,
                clipboard_fallback=self._config.clipboard_fallback,
                target_app=self._target_app,
            )
            self._dbg(f"PASTE result: {status}")
            if status == "clipboard":
                logger.info("Copied to clipboard (no text field).")
                self._pill.show_notification("Copied to clipboard")
            else:
                logger.info("Pasted.")
                self._pill.set_state("idle")
        else:
            logger.info("No speech detected.")
            self._pill.set_state("idle")

        if self._config.dynamic_loading:
            self._unload_all_models()

    @pyqtSlot(str)
    def _on_transcription_error(self, msg: str):
        self._transcribing = False
        self._pill.set_state("idle")
        logger.error("Transcription error: %s", msg)

        if self._config.dynamic_loading:
            self._unload_all_models()

    # ------------------------------------------------------------------
    # Model unloading
    # ------------------------------------------------------------------

    def _unload_all_models(self):
        """Unload all models and free GPU memory."""
        self._engine.unload_model()
        self._model_ready = False
        if self._extractor.is_loaded:
            self._extractor.unload_model()
            self._vlm_ready = False
        if self._corrector.is_loaded:
            self._corrector.unload_model()
            self._corrector_ready = False
        try:
            import gc
            gc.collect()
            import mlx.core as mx
            mx.metal.clear_cache()
        except Exception:
            pass
        logger.info("Models unloaded.")

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    @pyqtSlot()
    def _show_settings(self):
        from keysay.ui.settings_window import SettingsWindow
        models_loaded = {
            "asr": self._model_ready,
            "vlm": self._vlm_ready,
            "corrector": self._corrector_ready,
        }
        dialog = SettingsWindow(self._config, models_loaded=models_loaded)
        dialog.settings_changed.connect(self._apply_settings)
        dialog.quit_requested.connect(self._quit)
        self._sig_history_updated.connect(dialog.refresh_history)
        dialog.exec()
        self._sig_history_updated.disconnect(dialog.refresh_history)
        # Re-assert pill window level after dialog closes
        if self._pill.isVisible() and hasattr(self._pill, '_ns_window') and self._pill._ns_window:
            try:
                from AppKit import NSStatusWindowLevel
                self._pill._ns_window.setLevel_(NSStatusWindowLevel)
            except Exception:
                pass

    @pyqtSlot(Config)
    def _apply_settings(self, new_config: Config):
        old = self._config
        self._config = new_config
        new_config.save()

        if (new_config.hotkey_keycode != old.hotkey_keycode
                or new_config.hotkey_is_modifier != old.hotkey_is_modifier):
            self._listener.update_keycode(
                new_config.hotkey_keycode,
                new_config.hotkey_is_modifier,
            )

        if new_config.active != old.active:
            self._set_active(new_config.active)

        # Skip model loading/unloading when dynamic loading is on
        # (models load on hotkey press, unload after transcription)
        if not new_config.dynamic_loading:
            if (new_config.model_id != old.model_id
                    or new_config.quantization != old.quantization):
                self._load_model_async()

            # VLM model handling
            if new_config.vlm_enabled:
                if new_config.vlm_model != old.vlm_model or not self._extractor.is_loaded:
                    self._load_vlm_async()
            elif not new_config.vlm_enabled and self._extractor.is_loaded:
                self._extractor.unload_model()
                self._vlm_ready = False

            # Corrector handling
            if new_config.correction_preset != "none":
                if not self._corrector.is_loaded:
                    self._load_corrector_async()
            elif new_config.correction_preset == "none" and self._corrector.is_loaded:
                self._corrector.unload_model()
                self._corrector_ready = False
        elif old.dynamic_loading != new_config.dynamic_loading:
            # Just switched to dynamic loading — unload everything
            if new_config.dynamic_loading:
                self._unload_all_models()

        logger.info("Settings applied.")

    def _set_active(self, active: bool):
        self._config.active = active
        self._config.save()
        self._tray.set_active(active)

        if active:
            self._listener.start()
            self._poll_timer.start()
            self._pill.restore_position(self._config.pill_x, self._config.pill_y)
            self._pill.show()
            if self._config.dynamic_loading:
                self._pill.set_state("idle")
            else:
                self._pill.set_state("loading")
                self._load_model_async()
                if self._config.vlm_enabled or self._config.correction_preset != "none":
                    self._load_vlm_and_corrector_async()
        else:
            self._config.pill_x, self._config.pill_y = self._pill.save_position()
            self._config.save()
            self._poll_timer.stop()
            self._listener.stop()
            self._pill.hide()
            self._recording = False
            self._unload_all_models()

    def _quit(self):
        self._poll_timer.stop()
        if self._pill.isVisible():
            self._config.pill_x, self._config.pill_y = self._pill.save_position()
            self._config.save()
        self._listener.stop()
        self._engine.unload_model()
        self._extractor.unload_model()
        self._corrector.unload_model()
        self._app.quit()
