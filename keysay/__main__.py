"""Entry point for keysay.

Usage:
    python -m keysay               # GUI mode (default)
    python -m keysay --no-gui      # Terminal-only mode
    python -m keysay [--model MODEL_ID] [--language LANG] [--context WORDS]
"""

import argparse
import logging
import sys
import threading

from keysay.config import Config


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="keysay",
        description="Press-to-dictate using Qwen3-ASR on macOS.",
    )
    parser.add_argument(
        "--no-gui",
        action="store_true",
        help="Run in terminal-only mode (no floating pill or tray icon).",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="HuggingFace model ID (default: from config or Qwen/Qwen3-ASR-1.7B)",
    )
    parser.add_argument(
        "--language",
        default=None,
        help='Language for ASR (e.g. "English"). Default: auto-detect.',
    )
    parser.add_argument(
        "--context",
        default=None,
        help="Context/hint words for ASR (space-separated).",
    )
    parser.add_argument(
        "--hotkey-keycode",
        type=int,
        default=None,
        help="Virtual keycode for the hotkey (default: 61 = Right Option).",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging.",
    )
    return parser.parse_args()


def main():
    args = _parse_args()

    log_fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    log_level = logging.DEBUG if args.verbose else logging.INFO

    # Console handler
    console_h = logging.StreamHandler(sys.stderr)
    console_h.setFormatter(log_fmt)
    logging.root.addHandler(console_h)
    logging.root.setLevel(log_level)

    # File handler (always enabled when verbose) — survives PyInstaller's stderr redirect
    if args.verbose:
        import os
        log_dir = os.path.expanduser("~/Library/Application Support/keysay")
        os.makedirs(log_dir, exist_ok=True)
        file_h = logging.FileHandler(os.path.join(log_dir, "keysay.log"), mode="w")
        file_h.setFormatter(log_fmt)
        logging.root.addHandler(file_h)
    logger = logging.getLogger("keysay")

    # -- GUI mode (default) -------------------------------------------------
    if not args.no_gui:
        import atexit, signal, subprocess, os

        # Find .app bundle path (for relaunch after macOS "Quit & Reopen")
        _bundle_path = None
        if getattr(sys, 'frozen', False):
            exe = os.path.realpath(sys.executable)
            idx = exe.find('.app/Contents/')
            if idx > 0:
                _bundle_path = exe[:idx + 4]

        # Only relaunch when macOS sends SIGTERM ("Quit & Reopen")
        _sigterm_received = False

        def _relaunch():
            if _sigterm_received and _bundle_path and os.path.isdir(_bundle_path):
                subprocess.Popen(['open', '-n', _bundle_path])

        atexit.register(_relaunch)

        def _handle_term(signum, frame):
            nonlocal _sigterm_received
            _sigterm_received = True
            from PyQt6.QtWidgets import QApplication
            qapp = QApplication.instance()
            if qapp:
                qapp.quit()

        signal.signal(signal.SIGTERM, _handle_term)

        from keysay.app import KeysayApp
        app = KeysayApp()
        sys.exit(app.run())

    # -- Terminal mode (--no-gui) -------------------------------------------
    cfg = Config.load()
    if args.model:
        cfg.model_id = args.model
    if args.language:
        cfg.language = args.language
    if args.context:
        cfg.context_words = args.context
    if args.hotkey_keycode is not None:
        cfg.hotkey_keycode = args.hotkey_keycode

    # -- Check accessibility ------------------------------------------------
    from keysay.hotkey.cgevent_listener import _check_accessibility

    if not _check_accessibility():
        logger.warning(
            "Accessibility permission not granted. The hotkey listener may "
            "not work. Go to System Settings > Privacy & Security > "
            "Accessibility and add your terminal / Python."
        )

    # -- Load ASR model -----------------------------------------------------
    from keysay.asr.engine import ASREngine

    engine = ASREngine()
    print(f"Loading model {cfg.model_id}...")
    try:
        engine.load_model(cfg.model_id)
    except Exception as exc:
        logger.error("Failed to load ASR model: %s", exc)
        sys.exit(1)
    print("Model loaded.")

    # -- Set up recorder ----------------------------------------------------
    from keysay.audio.recorder import Recorder, MicrophoneNotFoundError

    recorder = Recorder()

    # -- Transcription lock (prevent overlapping transcriptions) ------------
    transcribing_lock = threading.Lock()

    # -- Hotkey callbacks ---------------------------------------------------
    def on_press():
        if not transcribing_lock.acquire(blocking=False):
            return  # Already transcribing, ignore this press.
        try:
            print("Recording...")
            recorder.start()
        except MicrophoneNotFoundError as exc:
            logger.error("Microphone error: %s", exc)
            transcribing_lock.release()
        except Exception as exc:
            logger.error("Failed to start recording: %s", exc)
            transcribing_lock.release()

    def on_release():
        # Run transcription in a separate thread to avoid blocking the
        # hotkey listener's CFRunLoop thread.
        def _do_transcribe():
            try:
                audio = recorder.stop()
                if audio.size == 0:
                    print("No audio captured.")
                    return

                duration = audio.size / 16_000
                print(f"Transcribing {duration:.1f}s of audio...")

                text = engine.transcribe(
                    audio,
                    language=cfg.language_for_asr,
                    context=cfg.context_for_asr,
                )

                if text:
                    print(f">>> {text}")
                    from keysay.paste.paster import paste_text
                    paste_text(text)
                else:
                    print("(no speech detected)")
            except Exception as exc:
                logger.error("Transcription failed: %s", exc)
            finally:
                transcribing_lock.release()

        threading.Thread(target=_do_transcribe, name="keysay-transcribe", daemon=True).start()

    # -- Start hotkey listener ----------------------------------------------
    from keysay.hotkey.cgevent_listener import HotkeyListener

    listener = HotkeyListener(
        keycode=cfg.hotkey_keycode,
        is_modifier=cfg.hotkey_is_modifier,
        on_press=on_press,
        on_release=on_release,
    )
    listener.start()

    hotkey_name = cfg.hotkey_name or f"keycode {cfg.hotkey_keycode}"
    print(f"\nkeysay ready. Press [{hotkey_name}] to record. Ctrl+C to quit.\n")

    # -- Block until Ctrl+C -------------------------------------------------
    try:
        threading.Event().wait()  # Block forever (interruptible by Ctrl+C).
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        listener.stop()
        engine.unload_model()
        print("Goodbye.")


if __name__ == "__main__":
    main()
