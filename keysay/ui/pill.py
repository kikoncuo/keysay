"""Floating pill — horizontal capsule, Wispr-style inline bar waveform."""

import logging
import math
import random
from collections import deque
from ctypes import c_void_p

logger = logging.getLogger(__name__)

from PyQt6.QtCore import (
    QEasingCurve,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    QTimer,
    pyqtProperty,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QColor,
    QGuiApplication,
    QPainter,
    QPen,
)
from PyQt6.QtWidgets import QWidget

from keysay.ui.theme import (
    Q_ACCENT,
    Q_SHADOW,
    Q_TEXT,
    Q_TEXT_SEC,
    Q_VOID,
    Q_BORDER,
    TEXT_SECONDARY,
    sans,
)

# ---------------------------------------------------------------------------
# Sizes — horizontal capsules
# ---------------------------------------------------------------------------
_IDLE_SIZE = QSize(120, 32)
_LOADING_SIZE = QSize(140, 32)
_ACTIVE_SIZE = QSize(180, 36)
_PROCESSING_SIZE = QSize(140, 32)
_NOTIFY_SIZE = QSize(200, 32)

_BOTTOM_MARGIN = 80

# Waveform config
_NUM_BARS = 10
_BAR_SMOOTHING = 0.35
_BAR_DECAY = 0.85


class FloatingPill(QWidget):
    """Horizontal capsule with inline bar waveform when recording."""

    settings_requested = pyqtSignal()

    _anim_w: int = _IDLE_SIZE.width()
    _anim_h: int = _IDLE_SIZE.height()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(_IDLE_SIZE)

        self._state = "idle"
        self._drag_pos: QPoint | None = None
        self._was_drag = False

        # Animation state
        self._sweep_angle = 0.0  # loading/processing arc sweep
        self._pulse_phase = 0.0  # sinusoidal pulse
        self._dot_phase = 0.0  # processing dots animation

        # Bar waveform state
        self._bars: list[float] = [0.0] * _NUM_BARS  # current 0-1
        self._targets: list[float] = [0.0] * _NUM_BARS
        self._rms_buffer: deque[float] = deque(maxlen=40)

        # Notify state
        self._notify_text: str = ""
        self._notify_timer: QTimer | None = None

        # Optional loading text (e.g. "Downloading...")
        self._loading_text: str = ""

        # --- size animation (center-anchored) ---
        self._size_anim = QPropertyAnimation(self, b"orbSize")
        self._size_anim.setDuration(250)
        self._size_anim.setEasingCurve(QEasingCurve.Type.OutBack)

        # Unified animation timer (60fps)
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(16)
        self._anim_timer.timeout.connect(self._anim_tick)

    # ------------------------------------------------------------------
    # Center-anchored size property
    # ------------------------------------------------------------------

    @pyqtProperty(QSize)
    def orbSize(self) -> QSize:  # noqa: N802
        return QSize(self._anim_w, self._anim_h)

    @orbSize.setter
    def orbSize(self, size: QSize) -> None:  # noqa: N802
        old_center = self.geometry().center()
        self._anim_w = size.width()
        self._anim_h = size.height()
        self.setFixedSize(size)
        # Keep center stable
        new_geo = self.geometry()
        new_geo.moveCenter(old_center)
        self.move(new_geo.topLeft())
        self.update()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_state(self, state: str) -> None:
        """Switch visual state: 'idle', 'loading', 'recording', 'processing', 'notify', or 'not_ready'."""
        logger.debug("Pill state: %s -> %s", self._state, state)
        if state == self._state:
            return
        self._loading_text = ""  # Clear loading text on state change
        self._state = state

        self._anim_timer.stop()

        if state == "idle":
            self._animate_to(_IDLE_SIZE)

        elif state == "loading":
            self._animate_to(_LOADING_SIZE)
            self._sweep_angle = 0.0
            self._anim_timer.start()

        elif state == "recording":
            self._animate_to(_ACTIVE_SIZE)
            self._bars = [0.0] * _NUM_BARS
            self._targets = [0.0] * _NUM_BARS
            self._anim_timer.start()

        elif state == "processing":
            self._animate_to(_PROCESSING_SIZE)
            self._sweep_angle = 0.0
            self._pulse_phase = 0.0
            self._dot_phase = 0.0
            self._anim_timer.start()

        elif state == "notify":
            self._animate_to(_NOTIFY_SIZE)
            self._pulse_phase = 0.0
            self._anim_timer.start()

        elif state == "not_ready":
            self._animate_to(_LOADING_SIZE)
            self._sweep_angle = 0.0
            self._anim_timer.start()
            QTimer.singleShot(
                1500,
                lambda: self.set_state("loading") if self._state == "not_ready" else None,
            )

        self.update()

    def set_loading_text(self, text: str) -> None:
        """Set text to display during loading state (e.g. 'Downloading...')."""
        self._loading_text = text
        self.update()

    def show_notification(self, text: str, duration_ms: int = 2000) -> None:
        """Show a brief text notification on the pill, then revert to idle."""
        self._notify_text = text
        self.set_state("notify")
        if self._notify_timer is not None:
            self._notify_timer.stop()
        self._notify_timer = QTimer(self)
        self._notify_timer.setSingleShot(True)
        self._notify_timer.timeout.connect(lambda: self.set_state("idle"))
        self._notify_timer.start(duration_ms)

    def update_waveform(self, rms_level: float) -> None:
        """Feed audio RMS to the bar waveform."""
        rms = max(0.0, min(1.0, rms_level))
        self._rms_buffer.append(rms)
        self._recompute_bar_targets()

    def save_position(self) -> tuple[int, int]:
        c = self.geometry().center()
        return c.x(), c.y()

    def restore_position(self, x: int, y: int) -> None:
        if x < 0 or y < 0:
            self._center_on_screen()
        else:
            geo = self.geometry()
            geo.moveCenter(QPoint(x, y))
            self.move(geo.topLeft())

    # ------------------------------------------------------------------
    # Bar target computation
    # ------------------------------------------------------------------

    def _recompute_bar_targets(self) -> None:
        if not self._rms_buffer:
            return
        latest = self._rms_buffer[-1]
        for i in range(_NUM_BARS):
            buf_idx = max(0, len(self._rms_buffer) - 1 - (i * 3 % max(1, len(self._rms_buffer))))
            sample = self._rms_buffer[buf_idx]
            mixed = sample * 0.6 + latest * 0.4
            jitter = random.uniform(-0.15, 0.15)
            self._targets[i] = max(0.0, min(1.0, mixed + jitter))

    # ------------------------------------------------------------------
    # Animation tick
    # ------------------------------------------------------------------

    def _anim_tick(self) -> None:
        if self._state == "recording":
            for i in range(_NUM_BARS):
                t = self._targets[i]
                c = self._bars[i]
                if t > c:
                    self._bars[i] = c + (t - c) * _BAR_SMOOTHING
                else:
                    self._bars[i] = c * _BAR_DECAY
                self._bars[i] = max(0.0, min(1.0, self._bars[i]))

        elif self._state in ("loading", "not_ready"):
            self._sweep_angle = (self._sweep_angle + 4) % 360.0

        elif self._state == "processing":
            self._sweep_angle = (self._sweep_angle + 5) % 360.0
            self._pulse_phase += 0.06
            self._dot_phase += 0.04

        elif self._state == "notify":
            self._pulse_phase += 0.03

        self.update()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _center_on_screen(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        x = geo.x() + geo.width() // 2
        y = geo.y() + geo.height() - self.height() // 2 - _BOTTOM_MARGIN
        rect = self.geometry()
        rect.moveCenter(QPoint(x, y))
        self.move(rect.topLeft())

    def _animate_to(self, target: QSize) -> None:
        self._size_anim.stop()
        self._size_anim.setStartValue(QSize(self._anim_w, self._anim_h))
        self._size_anim.setEndValue(target)
        self._size_anim.start()

    # ------------------------------------------------------------------
    # Painting
    # ------------------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        r = h / 2  # corner radius for capsule

        if self._state == "recording":
            self._paint_recording(p, w, h, r)
        elif self._state in ("loading", "not_ready"):
            self._paint_loading(p, w, h, r)
        elif self._state == "processing":
            self._paint_processing(p, w, h, r)
        elif self._state == "notify":
            self._paint_notify(p, w, h, r)
        else:
            self._paint_idle(p, w, h, r)

        p.end()

    def _draw_capsule_bg(self, p: QPainter, w: float, h: float, r: float) -> None:
        """Draw the standard dark capsule background with shadow and border."""
        # Shadow
        p.setPen(Qt.PenStyle.NoPen)
        shadow = QColor(0, 0, 0, 50)
        p.setBrush(shadow)
        p.drawRoundedRect(QRectF(1, 2, w - 2, h - 2), r, r)

        # Dark fill
        p.setBrush(Q_VOID)
        p.drawRoundedRect(QRectF(0, 0, w, h), r, r)

        # Subtle border
        p.setPen(QPen(Q_BORDER, 1.0))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), r, r)

    def _paint_idle(self, p: QPainter, w: float, h: float, r: float) -> None:
        self._draw_capsule_bg(p, w, h, r)

        # Small centered mic icon
        cx, cy = w / 2, h / 2
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(Q_TEXT_SEC)
        dot_r = 2.5
        p.drawEllipse(QPointF(cx, cy - 1.5), dot_r, dot_r)
        pen = QPen(Q_TEXT_SEC, 1.2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        arc_r = 4
        p.drawArc(
            QRectF(cx - arc_r, cy - 1.5 - arc_r, arc_r * 2, arc_r * 2),
            -40 * 16, -100 * 16,
        )
        p.drawLine(QPointF(cx, cy + 2.5), QPointF(cx, cy + 5))

    def _paint_loading(self, p: QPainter, w: float, h: float, r: float) -> None:
        self._draw_capsule_bg(p, w, h, r)

        if self._loading_text:
            # Text + thin animated bar at bottom
            p.setPen(QColor(Q_TEXT_SEC))
            p.setFont(sans(10))
            p.drawText(
                QRectF(8, 0, w - 16, h - 6),
                Qt.AlignmentFlag.AlignCenter,
                self._loading_text,
            )
            bar_w = w * 0.6
            bar_h = 2
            bar_x = (w - bar_w) / 2
            bar_y = h - 8
        else:
            # Thin horizontal progress indicator — animated sweep
            bar_w = w * 0.5
            bar_h = 2.5
            bar_x = w / 2 - bar_w / 2
            bar_y = h / 2 - bar_h / 2

        # Background track
        track_color = QColor(Q_BORDER)
        track_color.setAlphaF(0.3)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(track_color)
        p.drawRoundedRect(QRectF(bar_x, bar_y, bar_w, bar_h), bar_h / 2, bar_h / 2)

        # Moving indicator
        progress = (self._sweep_angle % 360) / 360.0
        ind_w = bar_w * 0.3
        ind_x = bar_x + progress * (bar_w - ind_w)
        p.setBrush(Q_ACCENT)
        p.drawRoundedRect(QRectF(ind_x, bar_y, ind_w, bar_h), bar_h / 2, bar_h / 2)

    def _paint_recording(self, p: QPainter, w: float, h: float, r: float) -> None:
        self._draw_capsule_bg(p, w, h, r)

        # Inline vertical bars — centered, monochrome
        cx, cy = w / 2, h / 2
        num = _NUM_BARS
        bar_spacing = 4.0
        bar_w = 2.5
        total_w = num * bar_w + (num - 1) * bar_spacing
        start_x = cx - total_w / 2
        max_bar_h = h * 0.55

        bar_color = QColor(TEXT_SECONDARY)

        for i in range(num):
            level = self._bars[i]
            bh = max(3.0, level * max_bar_h)
            bx = start_x + i * (bar_w + bar_spacing)
            by = cy - bh / 2

            bar_color.setAlphaF(0.5 + 0.5 * level)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(bar_color)
            p.drawRoundedRect(QRectF(bx, by, bar_w, bh), bar_w / 2, bar_w / 2)

    def _paint_processing(self, p: QPainter, w: float, h: float, r: float) -> None:
        pulse = 0.6 + 0.4 * math.sin(self._pulse_phase)

        self._draw_capsule_bg(p, w, h, r)

        # Subtle accent tint
        tint = QColor(Q_ACCENT)
        tint.setAlphaF(0.06 * pulse)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(tint)
        p.drawRoundedRect(QRectF(0, 0, w, h), r, r)

        # Three animated dots
        cx, cy = w / 2, h / 2
        p.setPen(Qt.PenStyle.NoPen)
        for i, dx in enumerate((-8, 0, 8)):
            phase = self._dot_phase + i * 0.7
            dot_alpha = 0.3 + 0.7 * (0.5 + 0.5 * math.sin(phase * math.pi * 2))
            dot_c = QColor(Q_TEXT)
            dot_c.setAlphaF(dot_alpha)
            p.setBrush(dot_c)
            p.drawEllipse(QPointF(cx + dx, cy), 2.5, 2.5)

    def _paint_notify(self, p: QPainter, w: float, h: float, r: float) -> None:
        self._draw_capsule_bg(p, w, h, r)

        # Subtle accent tint
        tint = QColor(Q_ACCENT)
        tint.setAlphaF(0.08)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(tint)
        p.drawRoundedRect(QRectF(0, 0, w, h), r, r)

        # Text
        p.setPen(QColor(Q_TEXT))
        p.setFont(sans(11))
        p.drawText(
            QRectF(8, 0, w - 16, h),
            Qt.AlignmentFlag.AlignCenter,
            self._notify_text,
        )

    # ------------------------------------------------------------------
    # Mouse events
    # ------------------------------------------------------------------

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._was_drag = False
            event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            self._was_drag = True
            event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and not self._was_drag:
            self.settings_requested.emit()
        self._drag_pos = None
        self._was_drag = False

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        self.settings_requested.emit()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if self.pos().x() <= 0 and self.pos().y() <= 0:
            self._center_on_screen()
        self._apply_macos_window_flags()

    def _apply_macos_window_flags(self) -> None:
        """Make the pill float above all apps and appear on all desktops."""
        try:
            import objc
            from AppKit import NSStatusWindowLevel
            # Get the NSView from the Qt winId, then get its NSWindow
            view_ptr = self.winId()
            if view_ptr is None:
                return
            ns_view = objc.objc_object(c_void_p=view_ptr.__int__())
            ns_window = ns_view.window()
            if ns_window is None:
                return
            ns_window.setLevel_(NSStatusWindowLevel)
            ns_window.setCollectionBehavior_(
                1 << 0   # canJoinAllSpaces
                | 1 << 4  # stationary
                | 1 << 9  # fullScreenAuxiliary
            )
            ns_window.setIgnoresMouseEvents_(False)
            ns_window.setHidesOnDeactivate_(False)
            self._ns_window = ns_window
        except Exception as e:
            # Fallback: try the old approach
            try:
                from AppKit import NSApp, NSStatusWindowLevel
                for window in NSApp.windows():
                    frame = window.frame()
                    geo = self.frameGeometry()
                    if (abs(frame.size.width - geo.width()) < 5
                            and abs(frame.size.height - geo.height()) < 5):
                        window.setLevel_(NSStatusWindowLevel)
                        window.setCollectionBehavior_(
                            1 << 0 | 1 << 4 | 1 << 9
                        )
                        window.setIgnoresMouseEvents_(False)
                        window.setHidesOnDeactivate_(False)
                        self._ns_window = window
                        break
            except Exception:
                pass
