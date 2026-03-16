"""Permission check dialog — card-based, live-polling, monochrome + coral."""

import subprocess

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from keysay.ui.theme import (
    ACCENT, ACCENT_HOVER,
    LT_BG, LT_CARD, LT_BORDER, LT_INPUT_BG,
    LT_TEXT, LT_TEXT_SEC, LT_TEXT_MUTED,
    STATE_ACTIVE,
    light_dialog_qss, mono, sans,
)


import logging
import sys

logger = logging.getLogger(__name__)


def check_accessibility() -> bool:
    logger.info("Checking accessibility... (pid=%s, exe=%s, frozen=%s)",
                __import__('os').getpid(), sys.executable, getattr(sys, 'frozen', False))
    try:
        from ApplicationServices import AXIsProcessTrusted
        result = AXIsProcessTrusted()
        logger.info("ApplicationServices.AXIsProcessTrusted() = %r (bool=%s)", result, bool(result))
        return bool(result)
    except ImportError as e:
        logger.info("ApplicationServices import failed: %s", e)
    try:
        from Quartz import AXIsProcessTrusted
        result = AXIsProcessTrusted()
        logger.info("Quartz.AXIsProcessTrusted() = %r (bool=%s)", result, bool(result))
        return bool(result)
    except ImportError as e:
        logger.info("Quartz import failed: %s", e)
    logger.info("All AX checks failed, returning True as fallback")
    return True


def check_microphone() -> bool:
    """Check microphone permission by opening a brief audio stream.

    Unlike query_devices(), opening an InputStream triggers the macOS
    microphone permission prompt if it hasn't been granted yet.
    """
    try:
        import sounddevice as sd
        with sd.InputStream(samplerate=16000, channels=1, blocksize=1024):
            pass
        return True
    except Exception as e:
        logger.info("Microphone check failed: %s", e)
        return False


def check_screen_recording() -> bool:
    """Check screen recording permission.

    CGPreflightScreenCaptureAccess (macOS 10.15+) checks without prompting.
    CGRequestScreenCaptureAccess triggers the OS prompt if not yet granted.
    """
    try:
        import ctypes
        import ctypes.util
        cg = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreGraphics"))
        cg.CGPreflightScreenCaptureAccess.restype = ctypes.c_bool
        if cg.CGPreflightScreenCaptureAccess():
            return True
        # Not granted — request it (triggers OS prompt)
        cg.CGRequestScreenCaptureAccess.restype = ctypes.c_bool
        cg.CGRequestScreenCaptureAccess()
        return False
    except Exception as e:
        logger.info("Screen recording check failed: %s", e)
        return True  # Assume granted if API unavailable


# Map permission keys to their check functions
_CHECKERS = {
    "accessibility": check_accessibility,
    "microphone": check_microphone,
    "screen_recording": check_screen_recording,
}


class PermissionsDialog(QDialog):
    def __init__(self, missing: list[str], parent: QWidget | None = None, bundled: bool = True) -> None:
        super().__init__(parent)
        self.setWindowTitle("keysay")
        self.setFixedWidth(460)
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint
        )
        self.setStyleSheet(light_dialog_qss())

        self._missing = list(missing)
        self._cards: dict[str, dict] = {}  # key -> {dot, btn, desc_label, granted}

        outer = QVBoxLayout(self)
        outer.setSpacing(16)
        outer.setContentsMargins(28, 24, 28, 24)

        # Header
        self._title = QLabel("Permissions needed")
        self._title.setFont(sans(20, QFont.Weight.Bold))
        outer.addWidget(self._title)

        self._desc = QLabel(
            "keysay needs these permissions to work. "
            "Grant them in System Settings."
        )
        self._desc.setWordWrap(True)
        self._desc.setFont(sans(13))
        self._desc.setStyleSheet(f"color: {LT_TEXT_SEC};")
        outer.addWidget(self._desc)

        # Hint about re-adding after rebuild (code signature changes invalidate permission)
        if bundled and "accessibility" in missing:
            hint = QLabel(
                "If keysay is already listed, remove it with \u2212 then re-add "
                "with +. Rebuilding the app changes its signature."
            )
            hint.setWordWrap(True)
            hint.setFont(sans(11))
            hint.setStyleSheet(
                f"color: {LT_TEXT_MUTED}; background: transparent; border: none;"
            )
            outer.addWidget(hint)

        # When not running as .app bundle, show which binary to add
        if not bundled and "accessibility" in missing:
            hint = QLabel(_python_binary_hint())
            hint.setWordWrap(True)
            hint.setFont(mono(11))
            hint.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            hint.setStyleSheet(
                f"color: {LT_TEXT_SEC}; background: {LT_INPUT_BG}; "
                f"border: 1px solid {LT_BORDER}; border-radius: 6px; padding: 8px;"
            )
            outer.addWidget(hint)

        outer.addSpacing(4)

        # Permission cards
        perm_map = {
            "accessibility": (
                "Accessibility",
                "Global hotkey detection and text pasting",
                self._open_accessibility,
            ),
            "microphone": (
                "Microphone",
                "Audio recording",
                self._open_microphone,
            ),
            "screen_recording": (
                "Screen Recording",
                "Screen context for better transcription",
                self._open_screen_recording,
            ),
            "input_monitoring": (
                "Input Monitoring",
                "Key event capture (macOS 14+)",
                self._open_input_monitoring,
            ),
        }

        for key in missing:
            if key in perm_map:
                name, desc_text, fn = perm_map[key]
                card, card_info = self._perm_card(key, name, desc_text, fn)
                self._cards[key] = card_info
                outer.addWidget(card)

        outer.addStretch()

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addStretch()

        quit_btn = QPushButton("Quit")
        quit_btn.setObjectName("ghostBtn")
        quit_btn.setFont(sans(13))
        quit_btn.clicked.connect(self._quit_app)
        btn_row.addWidget(quit_btn)

        self._cont_btn = QPushButton("Quit & Reopen")
        self._cont_btn.setFont(sans(13))
        self._cont_btn.clicked.connect(self._quit_app)
        btn_row.addWidget(self._cont_btn)

        outer.addLayout(btn_row)

        # Poll for permission changes every second
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(1000)
        self._poll_timer.timeout.connect(self._poll_permissions)
        self._poll_timer.start()

    def _perm_card(self, key: str, name: str, description: str, open_fn) -> tuple[QFrame, dict]:
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background: {LT_CARD};
                border: 1px solid {LT_BORDER};
                border-radius: 12px;
            }}
        """)

        layout = QHBoxLayout(card)
        layout.setSpacing(14)
        layout.setContentsMargins(16, 14, 16, 14)

        # Status dot (red = missing)
        dot = QWidget()
        dot.setFixedSize(8, 8)
        dot.setStyleSheet(f"background: {ACCENT}; border-radius: 4px;")
        layout.addWidget(dot, 0, Qt.AlignmentFlag.AlignTop)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        lbl = QLabel(name)
        lbl.setFont(sans(14, QFont.Weight.DemiBold))
        lbl.setStyleSheet(f"color: {LT_TEXT}; background: transparent; border: none;")
        desc_label = QLabel(description)
        desc_label.setFont(sans(12))
        desc_label.setStyleSheet(f"color: {LT_TEXT_MUTED}; background: transparent; border: none;")
        text_col.addWidget(lbl)
        text_col.addWidget(desc_label)
        layout.addLayout(text_col, 1)

        btn = QPushButton("Open")
        btn.setFixedWidth(70)
        btn.setFont(sans(12, QFont.Weight.DemiBold))
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {ACCENT}; color: #ffffff;
                border: none; border-radius: 8px; padding: 6px;
            }}
            QPushButton:hover {{ background: {ACCENT_HOVER}; }}
        """)
        btn.clicked.connect(open_fn)
        layout.addWidget(btn, 0, Qt.AlignmentFlag.AlignVCenter)

        card_info = {
            "dot": dot,
            "btn": btn,
            "desc_label": desc_label,
            "card": card,
            "granted": False,
        }
        return card, card_info

    def _mark_granted(self, info: dict) -> None:
        """Update a permission card to show granted state.

        Button stays clickable — permission checks can give false positives,
        so users should always be able to open System Settings.
        """
        info["granted"] = True
        info["dot"].setStyleSheet(f"background: {STATE_ACTIVE}; border-radius: 4px;")
        info["desc_label"].setText("Looks granted \u2014 open settings to verify")
        info["desc_label"].setStyleSheet(f"color: {STATE_ACTIVE}; background: transparent; border: none;")
        # Keep button enabled so users can always open System Settings
        info["btn"].setText("Open")

    def _mark_needs_restart(self, info: dict) -> None:
        """Update a permission card to show restart-required state."""
        info["granted"] = True  # Count as resolved for auto-dismiss
        info["dot"].setStyleSheet(f"background: #f5a623; border-radius: 4px;")
        info["desc_label"].setText("May need restart \u2014 open settings to check")
        info["desc_label"].setStyleSheet(f"color: #f5a623; background: transparent; border: none;")
        # Keep button enabled
        info["btn"].setText("Open")

    def _poll_permissions(self) -> None:
        all_granted = True
        for key, info in self._cards.items():
            if info["granted"]:
                continue
            checker = _CHECKERS.get(key)
            if checker is None:
                continue

            # Screen recording can't be detected live — macOS caches the
            # result per-process. Check if the user granted it by trying
            # a test screenshot instead.
            if key == "screen_recording":
                if self._check_screen_recording_via_screenshot():
                    self._mark_needs_restart(info)
                else:
                    all_granted = False
                continue

            granted = checker()
            if granted:
                self._mark_granted(info)
            else:
                all_granted = False

        if all_granted:
            self._poll_timer.stop()
            self._title.setText("Ready")
            self._desc.setText(
                "Permissions look good. If anything isn't working, "
                "open System Settings and verify each permission is enabled."
            )
            self._cont_btn.setText("Quit & Reopen")

    @staticmethod
    def _check_screen_recording_via_screenshot() -> bool:
        """Check screen recording by attempting a tiny screenshot.

        CGPreflightScreenCaptureAccess caches its result, so we use
        screencapture which reflects the current permission state.
        """
        import tempfile
        try:
            result = subprocess.run(
                ["screencapture", "-x", "-C", "-R", "0,0,1,1", tempfile.mktemp(suffix=".png")],
                capture_output=True, timeout=3,
            )
            return result.returncode == 0
        except Exception:
            return False

    def _quit_app(self):
        """Force-quit the entire application."""
        self._poll_timer.stop()
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance()
        if app:
            app.quit()
        sys.exit(0)

    @staticmethod
    def _open_accessibility():
        subprocess.Popen([
            "open", "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
        ])

    @staticmethod
    def _open_microphone():
        subprocess.Popen([
            "open", "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone"
        ])

    @staticmethod
    def _open_screen_recording():
        subprocess.Popen([
            "open", "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"
        ])

    @staticmethod
    def _open_input_monitoring():
        subprocess.Popen([
            "open", "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent"
        ])


def _is_bundled_app() -> bool:
    """Return True if running inside a .app bundle."""
    import sys
    return getattr(sys, 'frozen', False) or '.app/Contents/' in sys.executable


def _python_binary_hint() -> str:
    """Return a hint about which binary to add to Accessibility."""
    import os, sys
    exe = os.path.realpath(sys.executable)
    return (
        f"Add this binary to System Settings \u2192 Accessibility:\n{exe}"
    )


def check_and_prompt() -> bool:
    """Check all permissions at startup. Blocks until granted or dismissed.

    Checks: Accessibility, Microphone, Screen Recording.
    Shows a dialog with live-polling — cards turn green as permissions
    are granted. Auto-dismisses when all are granted.
    """
    missing = []
    if not check_accessibility():
        missing.append("accessibility")
    if not check_microphone():
        missing.append("microphone")
    if not check_screen_recording():
        missing.append("screen_recording")
    logger.info("Permission check: missing=%s", missing)
    if not missing:
        return True

    dialog = PermissionsDialog(missing, bundled=_is_bundled_app())
    result = dialog.exec()
    return result == QDialog.DialogCode.Accepted
