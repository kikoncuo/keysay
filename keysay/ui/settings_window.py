"""Settings window — warm light theme, sidebar navigation, auto-save."""

import os

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from keysay.config import (
    ASR_RAM_ESTIMATES,
    CORRECTION_RAM_ESTIMATE,
    Config,
    HOTKEY_PRESETS,
    SUPPORTED_LANGUAGES,
    SUPPORTED_MODELS,
    SUPPORTED_QUANTIZATIONS,
    VLM_MODELS,
    get_system_ram_gb,
)
from keysay.llm.presets import PRESET_CHOICES
from keysay.ui.theme import (
    ACCENT, ACCENT_HOVER,
    LT_BG, LT_BG_SIDEBAR, LT_CARD, LT_BORDER, LT_BORDER_HOVER,
    LT_HOVER, LT_INPUT_BG, LT_TEXT, LT_TEXT_SEC, LT_TEXT_MUTED, LT_ACCENT,
    STATE_ACTIVE, STATE_INACTIVE,
    light_dialog_qss, mono, sans,
)


# ---------------------------------------------------------------------------
# Styled combo box — forces Qt-rendered popup instead of native macOS
# ---------------------------------------------------------------------------

def _styled_combo() -> QComboBox:
    combo = QComboBox()
    combo.setView(QListView())
    return combo


# ---------------------------------------------------------------------------
# Custom painted toggle
# ---------------------------------------------------------------------------

class _Toggle(QWidget):
    toggled = pyqtSignal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(44, 24)
        self._on = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def is_on(self) -> bool:
        return self._on

    def set_on(self, on: bool) -> None:
        self._on = on
        self.update()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        self._on = not self._on
        self.update()
        self.toggled.emit(self._on)

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        r = h / 2
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(STATE_ACTIVE if self._on else LT_INPUT_BG))
        p.drawRoundedRect(0, 0, w, h, r, r)
        if not self._on:
            p.setPen(QPen(QColor(LT_BORDER), 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(0, 0, w, h, r, r)
        thumb_d = h - 4
        thumb_x = w - thumb_d - 2 if self._on else 2
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#fff"))
        p.drawEllipse(thumb_x, 2, thumb_d, thumb_d)
        p.end()


# ---------------------------------------------------------------------------
# Status banner
# ---------------------------------------------------------------------------

class _StatusBanner(QWidget):
    toggled = pyqtSignal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._active = True
        self.setFixedHeight(48)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def is_active(self) -> bool:
        return self._active

    def set_active(self, active: bool) -> None:
        self._active = active
        self.update()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        self._active = not self._active
        self.update()
        self.toggled.emit(self._active)

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(LT_CARD))
        p.drawRoundedRect(0, 0, w, h, 10, 10)
        p.setPen(QPen(QColor(LT_BORDER), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(0, 0, w, h, 10, 10)
        dot_x, dot_y = 18, h // 2
        dot_r = 5
        p.setPen(Qt.PenStyle.NoPen)
        if self._active:
            glow = QColor(STATE_ACTIVE)
            glow.setAlphaF(0.25)
            p.setBrush(glow)
            p.drawEllipse(dot_x - 8, dot_y - 8, 16, 16)
            p.setBrush(QColor(STATE_ACTIVE))
        else:
            p.setBrush(QColor(STATE_INACTIVE))
        p.drawEllipse(dot_x - dot_r, dot_y - dot_r, dot_r * 2, dot_r * 2)
        p.setPen(QColor(LT_TEXT))
        p.setFont(sans(14, QFont.Weight.DemiBold))
        p.drawText(36, 0, w - 80, h, Qt.AlignmentFlag.AlignVCenter,
                   "Loaded" if self._active else "Unloaded")
        p.setPen(QColor(LT_TEXT_MUTED))
        p.setFont(sans(11))
        p.drawText(w - 110, 0, 100, h,
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                   "tap to toggle")
        p.end()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _card() -> QFrame:
    f = QFrame()
    f.setStyleSheet(f"""
        QFrame {{
            background: {LT_CARD};
            border: 1px solid {LT_BORDER};
            border-radius: 10px;
        }}
    """)
    return f

def _label(text: str) -> QLabel:
    l = QLabel(text)
    l.setFont(sans(12))
    l.setStyleSheet(f"color: {LT_TEXT_SEC};")
    return l

def _section_title(text: str) -> QLabel:
    l = QLabel(text)
    l.setFont(sans(16, QFont.Weight.DemiBold))
    l.setStyleSheet(f"color: {LT_TEXT};")
    l.setContentsMargins(0, 0, 0, 8)
    return l

class _InfoIcon(QLabel):
    """Small info icon with a custom popup on hover."""

    def __init__(self, tooltip_text: str, parent: QWidget | None = None) -> None:
        super().__init__("\u24d8", parent)
        self._tooltip_text = tooltip_text
        self._popup: QLabel | None = None
        self.setFont(sans(12))
        self.setCursor(Qt.CursorShape.WhatsThisCursor)
        self.setStyleSheet(f"""
            QLabel {{
                color: {LT_TEXT_MUTED}; background: transparent; border: none;
                padding: 0 2px;
            }}
        """)

    def enterEvent(self, event) -> None:
        if self._popup is None:
            self._popup = QLabel(self._tooltip_text)
            self._popup.setWindowFlags(
                Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint
            )
            self._popup.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
            self._popup.setFont(sans(11))
            self._popup.setWordWrap(True)
            self._popup.setFixedWidth(260)
            self._popup.setStyleSheet(f"""
                QLabel {{
                    background: {LT_CARD};
                    color: {LT_TEXT_SEC};
                    border: 1px solid {LT_BORDER};
                    border-radius: 8px;
                    padding: 10px 12px;
                }}
            """)
        # Position below-right of the icon
        pos = self.mapToGlobal(self.rect().bottomLeft())
        self._popup.adjustSize()
        self._popup.move(pos.x() - 20, pos.y() + 4)
        self._popup.show()
        self.setStyleSheet(f"""
            QLabel {{
                color: {LT_ACCENT}; background: transparent; border: none;
                padding: 0 2px;
            }}
        """)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        if self._popup is not None:
            self._popup.hide()
        self.setStyleSheet(f"""
            QLabel {{
                color: {LT_TEXT_MUTED}; background: transparent; border: none;
                padding: 0 2px;
            }}
        """)
        super().leaveEvent(event)


def _info(tooltip: str) -> _InfoIcon:
    """Small info icon that shows a styled popup on hover."""
    return _InfoIcon(tooltip)

def _label_with_info(text: str, tooltip: str) -> QWidget:
    """Label + info icon in a row."""
    row = QWidget()
    row.setStyleSheet("background: transparent; border: none;")
    h = QHBoxLayout(row)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(4)
    l = QLabel(text)
    l.setFont(sans(12))
    l.setStyleSheet(f"color: {LT_TEXT_SEC}; background: transparent; border: none;")
    h.addWidget(l)
    h.addWidget(_info(tooltip))
    h.addStretch()
    return row


# ---------------------------------------------------------------------------
# Tag input
# ---------------------------------------------------------------------------

class _TagInput(QWidget):
    changed = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tags: list[str] = []
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(6)
        self._chips_row = QHBoxLayout()
        self._chips_row.setSpacing(6)
        self._chips_row.addStretch()
        self._layout.addLayout(self._chips_row)
        input_row = QHBoxLayout()
        input_row.setSpacing(6)
        self._input = QLineEdit()
        self._input.setPlaceholderText("Type a word")
        self._input.setFont(mono(12))
        self._input.returnPressed.connect(self._add)
        input_row.addWidget(self._input, 1)
        add_btn = QPushButton("Add")
        add_btn.setFont(sans(12))
        add_btn.setFixedWidth(60)
        add_btn.clicked.connect(lambda: self._add())
        input_row.addWidget(add_btn)
        self._layout.addLayout(input_row)

    def set_tags(self, tags: list[str]) -> None:
        self._tags = list(tags)
        self._rebuild()

    def get_tags(self) -> list[str]:
        return list(self._tags)

    def _add(self) -> None:
        w = self._input.text().strip()
        if w and w not in self._tags:
            self._tags.append(w)
            self._rebuild()
            self.changed.emit()
        self._input.clear()

    def _remove(self, tag: str) -> None:
        if tag in self._tags:
            self._tags.remove(tag)
            self._rebuild()
            self.changed.emit()

    def _rebuild(self) -> None:
        while self._chips_row.count() > 1:
            item = self._chips_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for tag in self._tags:
            chip = QPushButton(f"{tag}  \u00d7")
            chip.setFont(mono(11))
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.setStyleSheet(f"""
                QPushButton {{
                    background: {LT_INPUT_BG}; color: {LT_TEXT};
                    border: 1px solid {LT_BORDER};
                    border-radius: 6px; padding: 3px 8px;
                }}
                QPushButton:hover {{ border-color: {LT_ACCENT}; color: {LT_ACCENT}; }}
            """)
            chip.clicked.connect(lambda _, t=tag: self._remove(t))
            self._chips_row.insertWidget(self._chips_row.count() - 1, chip)


# ---------------------------------------------------------------------------
# Replacements editor
# ---------------------------------------------------------------------------

class _ReplacementsEditor(QWidget):
    changed = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)
        self._rows_layout = QVBoxLayout()
        self._rows_layout.setSpacing(6)
        outer.addLayout(self._rows_layout)
        add_btn = QPushButton("+ Add rule")
        add_btn.setFont(sans(12))
        add_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {LT_ACCENT};
                border: 1px dashed {LT_BORDER}; border-radius: 8px; padding: 5px;
            }}
            QPushButton:hover {{ border-color: {LT_ACCENT}; }}
        """)
        add_btn.clicked.connect(lambda: self._add_row())
        outer.addWidget(add_btn)

    def set_pairs(self, pairs: list[list[str]]) -> None:
        self._clear()
        for pair in pairs:
            if len(pair) == 2:
                self._add_row(pair[0], pair[1])

    def get_pairs(self) -> list[list[str]]:
        pairs = []
        for i in range(self._rows_layout.count()):
            item = self._rows_layout.itemAt(i)
            if item and item.layout():
                row = item.layout()
                fw, rw = row.itemAt(0), row.itemAt(2)
                if fw and rw and fw.widget() and rw.widget():
                    f, r = fw.widget(), rw.widget()
                    if isinstance(f, QLineEdit) and isinstance(r, QLineEdit):
                        ft = f.text().strip()
                        if ft:
                            pairs.append([ft, r.text().strip()])
        return pairs

    def _add_row(self, find_text: str = "", replace_text: str = "") -> None:
        row = QHBoxLayout()
        row.setSpacing(6)
        fe = QLineEdit(find_text)
        fe.setPlaceholderText("find")
        fe.setFont(mono(12))
        fe.editingFinished.connect(self.changed.emit)
        arrow = QLabel("\u2192")
        arrow.setFont(sans(13))
        arrow.setStyleSheet(f"color: {LT_TEXT_MUTED};")
        arrow.setFixedWidth(18)
        arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
        re = QLineEdit(replace_text)
        re.setPlaceholderText("replace")
        re.setFont(mono(12))
        re.editingFinished.connect(self.changed.emit)
        rm = QPushButton("\u00d7")
        rm.setFixedSize(26, 26)
        rm.setStyleSheet(f"""
            QPushButton {{ color: {LT_TEXT_MUTED}; background: transparent; border: none; font-size: 15px; }}
            QPushButton:hover {{ color: {LT_ACCENT}; }}
        """)
        rm.clicked.connect(lambda: self._remove_row(row))
        row.addWidget(fe, 1)
        row.addWidget(arrow)
        row.addWidget(re, 1)
        row.addWidget(rm)
        self._rows_layout.addLayout(row)

    def _remove_row(self, row_layout) -> None:
        while row_layout.count():
            item = row_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._rows_layout.removeItem(row_layout)
        self.changed.emit()

    def _clear(self) -> None:
        while self._rows_layout.count():
            item = self._rows_layout.takeAt(0)
            if item.layout():
                while item.layout().count():
                    sub = item.layout().takeAt(0)
                    if sub.widget():
                        sub.widget().deleteLater()


# ---------------------------------------------------------------------------
# Sidebar button
# ---------------------------------------------------------------------------

class _SidebarButton(QPushButton):
    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setFont(sans(13))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setCheckable(True)
        self.setFixedHeight(36)
        self._update_style()

    def _update_style(self) -> None:
        self.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {LT_TEXT_SEC};
                border: none;
                border-radius: 8px;
                padding: 4px 12px;
                text-align: left;
            }}
            QPushButton:hover {{
                background: {LT_HOVER};
                color: {LT_TEXT};
            }}
            QPushButton:checked {{
                background: {LT_CARD};
                color: {LT_TEXT};
                font-weight: 600;
                border: 1px solid {LT_BORDER};
            }}
        """)


# ---------------------------------------------------------------------------
# RAM status bar (painted)
# ---------------------------------------------------------------------------

class _RamStatusBar(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(36)
        self._system_ram = get_system_ram_gb()
        self._segments: list[tuple[str, float, str]] = []  # (label, gb, color)

    def set_segments(self, segments: list[tuple[str, float, str]]) -> None:
        """Set RAM segments: [(label, gb, color), ...]"""
        self._segments = segments
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        # Background
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(LT_BG_SIDEBAR))
        p.drawRect(0, 0, w, h)

        # Top border
        p.setPen(QPen(QColor(LT_BORDER), 1))
        p.drawLine(0, 0, w, 0)

        total_model = sum(s[1] for s in self._segments)
        if self._system_ram <= 0:
            p.end()
            return

        # Bar
        bar_x, bar_y = 16, 8
        bar_w, bar_h = w - 32, 6
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(LT_BORDER))
        p.drawRoundedRect(bar_x, bar_y, bar_w, bar_h, bar_h // 2, bar_h // 2)

        # Stacked segments
        x = bar_x
        for _label, gb, color in self._segments:
            if gb <= 0:
                continue
            seg_w = max(1, int(bar_w * gb / self._system_ram))
            p.setBrush(QColor(color))
            p.drawRoundedRect(int(x), bar_y, seg_w, bar_h, bar_h // 2, bar_h // 2)
            x += seg_w

        # Legend text below bar
        p.setFont(sans(9))
        tx = bar_x
        for label, gb, color in self._segments:
            if gb <= 0:
                continue
            # Colored dot
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(color))
            p.drawEllipse(int(tx), 19, 6, 6)
            # Label
            p.setPen(QColor(LT_TEXT_MUTED))
            text = f"{label} {gb:.1f}G"
            fm = p.fontMetrics()
            tw = fm.horizontalAdvance(text)
            p.drawText(int(tx) + 9, 18, tw, 14, Qt.AlignmentFlag.AlignVCenter, text)
            tx += tw + 20

        # Total / System on right
        p.setPen(QColor(LT_TEXT_MUTED))
        p.setFont(sans(9))
        summary = f"{total_model:.1f} / {self._system_ram:.0f} GB"
        fm = p.fontMetrics()
        sw = fm.horizontalAdvance(summary)
        p.drawText(w - sw - 16, 18, sw, 14, Qt.AlignmentFlag.AlignVCenter, summary)

        p.end()


# ---------------------------------------------------------------------------
# Settings window
# ---------------------------------------------------------------------------

class SettingsWindow(QDialog):
    settings_changed = pyqtSignal(Config)
    quit_requested = pyqtSignal()

    def __init__(self, config: Config, models_loaded: dict | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("keysay")
        self.setFixedSize(700, 560)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self.setStyleSheet(light_dialog_qss())
        icon_path = os.path.join(os.path.dirname(__file__), "icon.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        self._config = config
        self._models_loaded = models_loaded or {"asr": True, "vlm": True, "corrector": True}
        self._populating = True
        self._build_ui()
        self._populate(config)
        self._populating = False
        self._update_ram_bar()
        self._update_dynamic_loading_ui()

    # ------------------------------------------------------------------
    # Auto-save
    # ------------------------------------------------------------------

    def _auto_save(self) -> None:
        if self._populating:
            return
        new_cfg = self._read_config()
        new_cfg.custom_prompts = self._config.custom_prompts
        self._config = new_cfg
        self._update_ram_bar()
        self.settings_changed.emit(new_cfg)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setSpacing(0)
        outer.setContentsMargins(0, 0, 0, 0)

        # ── Header ──
        header = QWidget()
        header.setStyleSheet(f"background: {LT_BG};")
        hdr_layout = QHBoxLayout(header)
        hdr_layout.setContentsMargins(24, 16, 24, 12)
        # App icon (Retina-aware: load at 2x and set devicePixelRatio)
        icon_path = os.path.join(os.path.dirname(__file__), "icon_256.png")
        if os.path.exists(icon_path):
            icon_label = QLabel()
            dpr = self.devicePixelRatioF()
            phys_size = int(32 * dpr)
            pixmap = QPixmap(icon_path).scaled(
                phys_size, phys_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            pixmap.setDevicePixelRatio(dpr)
            icon_label.setPixmap(pixmap)
            icon_label.setFixedSize(32, 32)
            icon_label.setStyleSheet("background: transparent; border: none;")
            hdr_layout.addWidget(icon_label)
            hdr_layout.addSpacing(8)

        title = QLabel("keysay")
        title.setFont(sans(20, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {LT_TEXT};")
        hdr_layout.addWidget(title)
        hdr_layout.addStretch()

        self._status_banner = _StatusBanner()
        self._status_banner.setFixedWidth(200)
        self._status_banner.toggled.connect(lambda _: self._auto_save())
        hdr_layout.addWidget(self._status_banner)

        hdr_layout.addSpacing(12)

        quit_btn = QPushButton("Quit")
        quit_btn.setFont(sans(12))
        quit_btn.setFixedHeight(30)
        quit_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {LT_TEXT_MUTED};
                border: 1px solid {LT_BORDER}; border-radius: 6px; padding: 0 14px;
            }}
            QPushButton:hover {{ color: #ff6b6b; border-color: #ff6b6b; }}
        """)
        quit_btn.clicked.connect(self._on_quit)
        hdr_layout.addWidget(quit_btn)
        outer.addWidget(header)

        # ── Separator ──
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {LT_BORDER};")
        outer.addWidget(sep)

        # ── Body: sidebar + content ──
        body = QHBoxLayout()
        body.setSpacing(0)
        body.setContentsMargins(0, 0, 0, 0)

        # Sidebar
        sidebar = QWidget()
        sidebar.setFixedWidth(160)
        sidebar.setStyleSheet(f"background: {LT_BG_SIDEBAR};")
        sb_layout = QVBoxLayout(sidebar)
        sb_layout.setContentsMargins(12, 16, 12, 16)
        sb_layout.setSpacing(4)

        self._sidebar_buttons: list[_SidebarButton] = []
        sections = ["Voice", "Recognition", "Screen Context", "Post-Processing", "Advanced", "History", "Models"]
        for i, name in enumerate(sections):
            btn = _SidebarButton(name)
            btn.clicked.connect(lambda checked, idx=i: self._switch_section(idx))
            self._sidebar_buttons.append(btn)
            sb_layout.addWidget(btn)
        sb_layout.addStretch()

        body.addWidget(sidebar)

        # Vertical separator
        vsep = QFrame()
        vsep.setFixedWidth(1)
        vsep.setStyleSheet(f"background: {LT_BORDER};")
        body.addWidget(vsep)

        # Content stack
        self._stack = QStackedWidget()
        self._stack.setStyleSheet(f"background: {LT_BG};")
        body.addWidget(self._stack, 1)

        outer.addLayout(body, 1)

        # ── RAM status bar at bottom ──
        self._ram_bar = _RamStatusBar()
        outer.addWidget(self._ram_bar)

        # Build section pages
        self._build_voice_section()
        self._build_model_section()
        self._build_vlm_section()
        self._build_postprocessing_section()
        self._build_advanced_section()
        self._build_history_section()
        self._build_models_section()

        # Select first section
        self._switch_section(0)

    def _switch_section(self, idx: int) -> None:
        for i, btn in enumerate(self._sidebar_buttons):
            btn.setChecked(i == idx)
        self._stack.setCurrentIndex(idx)

    # ------------------------------------------------------------------
    # Section builders
    # ------------------------------------------------------------------

    def _make_section_page(self) -> tuple[QWidget, QVBoxLayout]:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent;")
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)
        scroll.setWidget(page)
        self._stack.addWidget(scroll)
        return page, layout

    def _build_voice_section(self) -> None:
        _, layout = self._make_section_page()
        layout.addWidget(_section_title("Voice"))

        card = _card()
        cl = QVBoxLayout(card)
        cl.setSpacing(10)
        cl.setContentsMargins(16, 16, 16, 16)

        cl.addWidget(_label_with_info("Microphone",
            "The audio input device used for recording.\n\n"
            "\"MacBook Pro Microphone\" is recommended for\n"
            "built-in use. External mics may provide\n"
            "better quality in noisy environments."))
        self._mic_combo = _styled_combo()
        self._mic_devices: list[tuple[int, str, bool]] = []
        try:
            from keysay.audio.recorder import list_input_devices
            self._mic_devices = list_input_devices()
        except Exception:
            pass
        # Add "System default" as first option
        default_name = "System default"
        for _idx, name, is_default in self._mic_devices:
            if is_default:
                default_name = f"System default ({name})"
                break
        self._mic_combo.addItem(default_name, -1)
        for dev_idx, name, is_default in self._mic_devices:
            display = f"{name} (recommended)" if "mac" in name.lower() else name
            self._mic_combo.addItem(display, dev_idx)
        self._mic_combo.setFont(mono(12))
        self._mic_combo.currentIndexChanged.connect(self._auto_save)
        cl.addWidget(self._mic_combo)

        cl.addSpacing(4)
        cl.addWidget(_label_with_info("Language",
            "Hint for the speech recognition model.\n\n"
            "\"Auto-detect\" works well for most cases.\n"
            "Setting a specific language improves accuracy\n"
            "if you always speak the same language."))
        self._language_combo = _styled_combo()
        self._language_combo.addItems(SUPPORTED_LANGUAGES)
        self._language_combo.setFont(mono(12))
        self._language_combo.currentIndexChanged.connect(self._auto_save)
        cl.addWidget(self._language_combo)

        cl.addSpacing(4)
        cl.addWidget(_label_with_info("Hotkey",
            "The key you hold down to record.\n\n"
            "Press and hold to start recording,\n"
            "release to stop and transcribe.\n"
            "Fn/Globe is recommended as it doesn't\n"
            "interfere with normal typing."))
        self._hotkey_combo = _styled_combo()
        for name, _kc, _mod in HOTKEY_PRESETS:
            self._hotkey_combo.addItem(name)
        self._hotkey_combo.setFont(mono(12))
        self._hotkey_combo.currentIndexChanged.connect(self._auto_save)
        cl.addWidget(self._hotkey_combo)

        layout.addWidget(card)
        layout.addStretch()

    def _build_model_section(self) -> None:
        _, layout = self._make_section_page()
        layout.addWidget(_section_title("Speech Recognition"))

        card = _card()
        cl = QVBoxLayout(card)
        cl.setSpacing(10)
        cl.setContentsMargins(16, 16, 16, 16)

        cl.addWidget(_label_with_info("ASR Model",
            "The speech recognition model that converts\n"
            "your voice to text. Runs locally on your Mac\n"
            "using Apple Silicon (MLX).\n\n"
            "1.7B: Best accuracy, uses ~5 GB RAM.\n"
            "0.6B: Faster, uses ~2 GB RAM."))
        self._model_combo = _styled_combo()
        for model_id, display in SUPPORTED_MODELS:
            self._model_combo.addItem(display, model_id)
        self._model_combo.setFont(mono(12))
        self._model_combo.currentIndexChanged.connect(self._update_ram_bar)
        self._model_combo.currentIndexChanged.connect(self._auto_save)
        cl.addWidget(self._model_combo)

        cl.addSpacing(4)
        cl.addWidget(_label_with_info("Quantization",
            "Reduces model size and RAM usage at the\n"
            "cost of slight accuracy loss.\n\n"
            "bf16: Full precision, best quality.\n"
            "q8: 8-bit, nearly identical quality, ~50% less RAM.\n"
            "q4: 4-bit, fastest, slight quality drop."))
        self._quant_combo = _styled_combo()
        for quant_id, display in SUPPORTED_QUANTIZATIONS:
            self._quant_combo.addItem(display, quant_id)
        self._quant_combo.setFont(mono(12))
        self._quant_combo.currentIndexChanged.connect(self._auto_save)
        cl.addWidget(self._quant_combo)

        cl.addSpacing(4)
        self._asr_ram_label = QLabel("")
        self._asr_ram_label.setFont(mono(11))
        self._asr_ram_label.setStyleSheet(f"color: {LT_TEXT_MUTED};")
        cl.addWidget(self._asr_ram_label)

        layout.addWidget(card)
        layout.addStretch()

    def _build_vlm_section(self) -> None:
        _, layout = self._make_section_page()
        layout.addWidget(_section_title("Screen Context"))

        card = _card()
        cl = QVBoxLayout(card)
        cl.setSpacing(10)
        cl.setContentsMargins(16, 16, 16, 16)

        toggle_row = QHBoxLayout()
        desc = QLabel("Read screen for ASR hints")
        desc.setFont(sans(12))
        desc.setStyleSheet(f"color: {LT_TEXT_SEC}; border: none; background: transparent;")
        toggle_row.addWidget(desc)
        toggle_row.addWidget(_info(
            "When you press the hotkey, keysay takes a\n"
            "screenshot and uses a vision model (VLM) to\n"
            "extract names, terms, and context from your\n"
            "screen. These are fed to the ASR model as\n"
            "hints so it correctly transcribes words it\n"
            "sees on screen.\n\n"
            "Example: if your screen shows \"Kubernetes\",\n"
            "the ASR will prefer \"Kubernetes\" over\n"
            "\"Cooper Netties\" when you say it."))
        toggle_row.addStretch()
        self._vlm_toggle = _Toggle()
        self._vlm_toggle.toggled.connect(self._on_vlm_toggled)
        self._vlm_toggle.toggled.connect(lambda _: self._auto_save())
        toggle_row.addWidget(self._vlm_toggle)
        cl.addLayout(toggle_row)

        cl.addSpacing(4)
        cl.addWidget(_label_with_info("VLM Model",
            "The vision-language model used to read your\n"
            "screen. Larger models extract more context\n"
            "but use more RAM.\n\n"
            "0.8B: Lightweight, good for basic context.\n"
            "2B: Better extraction, recommended.\n"
            "4B/9B: Most thorough, needs more RAM."))
        self._vlm_model_combo = _styled_combo()
        for model_id, display, _ram in VLM_MODELS:
            self._vlm_model_combo.addItem(display, model_id)
        self._vlm_model_combo.setFont(mono(12))
        self._vlm_model_combo.currentIndexChanged.connect(self._update_ram_bar)
        self._vlm_model_combo.currentIndexChanged.connect(self._auto_save)
        cl.addWidget(self._vlm_model_combo)

        cl.addSpacing(4)
        self._vlm_ram_label = QLabel("")
        self._vlm_ram_label.setFont(mono(11))
        self._vlm_ram_label.setStyleSheet(f"color: {LT_TEXT_MUTED};")
        cl.addWidget(self._vlm_ram_label)

        layout.addWidget(card)
        layout.addStretch()

    def _build_postprocessing_section(self) -> None:
        _, layout = self._make_section_page()
        layout.addWidget(_section_title("Post-Processing"))

        card = _card()
        cl = QVBoxLayout(card)
        cl.setSpacing(10)
        cl.setContentsMargins(16, 16, 16, 16)

        desc_row = QHBoxLayout()
        desc = QLabel("Clean up text after transcription")
        desc.setFont(sans(12))
        desc.setStyleSheet(f"color: {LT_TEXT_SEC}; border: none; background: transparent;")
        desc_row.addWidget(desc)
        desc_row.addWidget(_info(
            "Runs a small language model on your\n"
            "transcription to clean it up before pasting.\n\n"
            "Removes filler words (um, uh), fixes\n"
            "self-corrections, and can reformat text\n"
            "based on the selected preset.\n\n"
            "Example: \"I want to um go to the the store\"\n"
            "becomes \"I want to go to the store\""))
        desc_row.addStretch()
        cl.addLayout(desc_row)

        cl.addSpacing(4)
        cl.addWidget(_label_with_info("Preset",
            "Each preset uses a different prompt to\n"
            "control how the text is cleaned.\n\n"
            "Clean utterances: Remove fillers only.\n"
            "Formal writing: Full sentences, proper grammar.\n"
            "Email style: Professional email tone.\n"
            "Notes/bullets: Convert to bullet points.\n"
            "Code dictation: Optimize for code terms."))
        self._correction_preset_combo = _styled_combo()
        for key, label_text in PRESET_CHOICES:
            self._correction_preset_combo.addItem(label_text, key)
        self._correction_preset_combo.setFont(mono(12))
        self._correction_preset_combo.currentIndexChanged.connect(self._update_ram_bar)
        self._correction_preset_combo.currentIndexChanged.connect(self._auto_save)
        cl.addWidget(self._correction_preset_combo)

        # Edit prompt button — full width, below combo
        self._edit_prompt_btn = QPushButton("Edit prompt")
        self._edit_prompt_btn.setFont(sans(12))
        self._edit_prompt_btn.clicked.connect(self._edit_prompt)
        cl.addWidget(self._edit_prompt_btn)

        cl.addSpacing(4)

        # Model info
        model_label = QLabel("Correction model")
        model_label.setFont(sans(11))
        model_label.setStyleSheet(f"color: {LT_TEXT_MUTED}; border: none; background: transparent;")
        cl.addWidget(model_label)
        self._correction_model_label = QLabel("")
        self._correction_model_label.setFont(mono(10))
        self._correction_model_label.setStyleSheet(f"color: {LT_TEXT_MUTED}; border: none; background: transparent;")
        self._correction_model_label.setWordWrap(True)
        cl.addWidget(self._correction_model_label)

        layout.addWidget(card)
        layout.addStretch()

    def _build_advanced_section(self) -> None:
        _, layout = self._make_section_page()
        layout.addWidget(_section_title("Advanced"))

        # Clipboard fallback
        cb_card = _card()
        cb_l = QVBoxLayout(cb_card)
        cb_l.setSpacing(10)
        cb_l.setContentsMargins(16, 16, 16, 16)

        cb_row = QHBoxLayout()
        cb_desc = QLabel("Copy to clipboard if no text field detected")
        cb_desc.setFont(sans(12))
        cb_desc.setStyleSheet(f"color: {LT_TEXT_SEC}; border: none; background: transparent;")
        cb_desc.setWordWrap(True)
        cb_row.addWidget(cb_desc, 1)
        cb_row.addWidget(_info(
            "When enabled, if keysay can't find a text\n"
            "field to paste into, the transcription is\n"
            "copied to your clipboard instead.\n\n"
            "You'll see a \"Copied to clipboard\" notification\n"
            "on the pill and can paste manually with Cmd+V."))
        self._clipboard_fallback_toggle = _Toggle()
        self._clipboard_fallback_toggle.toggled.connect(lambda _: self._auto_save())
        cb_row.addWidget(self._clipboard_fallback_toggle)
        cb_l.addLayout(cb_row)

        layout.addWidget(cb_card)

        # Dynamic loading
        dl_card = _card()
        dl_l = QVBoxLayout(dl_card)
        dl_l.setSpacing(10)
        dl_l.setContentsMargins(16, 16, 16, 16)

        dl_row = QHBoxLayout()
        dl_desc = QLabel("Dynamic loading")
        dl_desc.setFont(sans(12))
        dl_desc.setStyleSheet(f"color: {LT_TEXT_SEC}; border: none; background: transparent;")
        dl_row.addWidget(dl_desc)
        dl_row.addWidget(_info(
            "When enabled, models are loaded into RAM\n"
            "only when you press the hotkey, and unloaded\n"
            "after each transcription.\n\n"
            "Saves RAM when keysay is idle, but adds\n"
            "a few seconds delay on the first press."))
        dl_row.addStretch()
        self._dynamic_loading_toggle = _Toggle()
        self._dynamic_loading_toggle.toggled.connect(lambda _: (self._update_dynamic_loading_ui(), self._update_ram_bar(), self._auto_save()))
        dl_row.addWidget(self._dynamic_loading_toggle)
        dl_l.addLayout(dl_row)

        dl_hint = QLabel("Load models when you press the hotkey, unload after each transcription to free RAM")
        dl_hint.setFont(sans(10))
        dl_hint.setStyleSheet(f"color: {LT_TEXT_MUTED}; border: none; background: transparent;")
        dl_hint.setWordWrap(True)
        dl_l.addWidget(dl_hint)

        layout.addWidget(dl_card)

        # Context words
        layout.addSpacing(4)
        ctx_row = QHBoxLayout()
        ctx_label = QLabel("Context Words")
        ctx_label.setFont(sans(13, QFont.Weight.DemiBold))
        ctx_label.setStyleSheet(f"color: {LT_TEXT};")
        ctx_row.addWidget(ctx_label)
        ctx_row.addWidget(_info(
            "Words and phrases the ASR model should\n"
            "listen for. These are always sent as hints\n"
            "to improve transcription accuracy.\n\n"
            "If Screen Context (VLM) is enabled, words\n"
            "extracted from your screen are combined\n"
            "with these manual hints automatically.\n\n"
            "Example: Add \"PyQt6\", \"keysay\", or names\n"
            "the model might not know."))
        ctx_row.addStretch()
        layout.addLayout(ctx_row)

        ctx_card = _card()
        ctx_l = QVBoxLayout(ctx_card)
        ctx_l.setContentsMargins(16, 16, 16, 16)
        self._tag_input = _TagInput()
        self._tag_input.changed.connect(self._auto_save)
        ctx_l.addWidget(self._tag_input)
        layout.addWidget(ctx_card)

        # Replacements
        layout.addSpacing(4)
        rep_row = QHBoxLayout()
        rep_label = QLabel("Replacements")
        rep_label.setFont(sans(13, QFont.Weight.DemiBold))
        rep_label.setStyleSheet(f"color: {LT_TEXT};")
        rep_row.addWidget(rep_label)
        rep_row.addWidget(_info(
            "Find-and-replace rules applied to every\n"
            "transcription before pasting.\n\n"
            "Runs after ASR but before post-processing.\n"
            "Useful for fixing consistent mistranscriptions\n"
            "or expanding abbreviations.\n\n"
            "Example: \"keysay\" -> \"KeySay\"\n"
            "Example: \"period\" -> \".\""))
        rep_row.addStretch()
        layout.addLayout(rep_row)

        rep_card = _card()
        rep_l = QVBoxLayout(rep_card)
        rep_l.setContentsMargins(16, 16, 16, 16)
        self._replacements = _ReplacementsEditor()
        self._replacements.changed.connect(self._auto_save)
        rep_l.addWidget(self._replacements)
        layout.addWidget(rep_card)

        layout.addStretch()

    # ------------------------------------------------------------------
    # History section
    # ------------------------------------------------------------------

    def _build_history_section(self) -> None:
        _, layout = self._make_section_page()

        title_row = QHBoxLayout()
        title_row.addWidget(_section_title("History"))
        title_row.addStretch()
        clear_btn = QPushButton("Clear")
        clear_btn.setFont(sans(11))
        clear_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {LT_TEXT_MUTED};
                border: 1px solid {LT_BORDER}; border-radius: 6px; padding: 4px 12px;
            }}
            QPushButton:hover {{ color: #ff6b6b; border-color: #ff6b6b; }}
        """)
        clear_btn.clicked.connect(self._clear_history)
        title_row.addWidget(clear_btn)
        layout.addLayout(title_row)

        self._history_container = QVBoxLayout()
        self._history_container.setSpacing(8)
        layout.addLayout(self._history_container)

        self._refresh_history()
        layout.addStretch()

    def _refresh_history(self) -> None:
        while self._history_container.count():
            item = self._history_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        from keysay.history import load_history
        entries = load_history()

        if not entries:
            empty = QLabel("No transcriptions yet")
            empty.setFont(sans(12))
            empty.setStyleSheet(f"color: {LT_TEXT_MUTED};")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._history_container.addWidget(empty)
            return

        for entry in reversed(entries[-50:]):
            self._history_container.addWidget(self._history_entry_card(entry))

    def _history_entry_card(self, entry: dict) -> QFrame:
        card = _card()
        cl = QVBoxLayout(card)
        cl.setContentsMargins(12, 10, 12, 10)
        cl.setSpacing(4)

        header = QHBoxLayout()
        from datetime import datetime
        try:
            ts = datetime.fromisoformat(entry["timestamp"])
            time_str = ts.strftime("%b %d, %I:%M %p")
        except (ValueError, KeyError):
            time_str = "Unknown"

        time_label = QLabel(time_str)
        time_label.setFont(sans(10))
        time_label.setStyleSheet(f"color: {LT_TEXT_MUTED}; background: transparent; border: none;")
        header.addWidget(time_label)

        duration = entry.get("duration_s", 0)
        if duration > 0:
            dur_label = QLabel(f"{duration:.1f}s")
            dur_label.setFont(mono(10))
            dur_label.setStyleSheet(f"color: {LT_TEXT_MUTED}; background: transparent; border: none;")
            header.addWidget(dur_label)

        header.addStretch()

        copy_btn = QPushButton("Copy")
        copy_btn.setFont(sans(10))
        copy_btn.setFixedHeight(22)
        copy_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {LT_ACCENT};
                border: 1px solid {LT_BORDER}; border-radius: 4px; padding: 0 8px;
            }}
            QPushButton:hover {{ border-color: {LT_ACCENT}; }}
        """)
        text = entry.get("text", "")
        copy_btn.clicked.connect(lambda _, t=text: self._copy_to_clipboard(t))
        header.addWidget(copy_btn)

        cl.addLayout(header)

        text_label = QLabel(text)
        text_label.setFont(mono(11))
        text_label.setWordWrap(True)
        text_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        text_label.setStyleSheet(f"color: {LT_TEXT}; background: transparent; border: none;")
        cl.addWidget(text_label)

        return card

    def _copy_to_clipboard(self, text: str) -> None:
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(text)

    def refresh_history(self) -> None:
        """Public slot — called when a new transcription is recorded."""
        if hasattr(self, '_history_container'):
            self._refresh_history()

    def _clear_history(self) -> None:
        from keysay.history import clear_history
        clear_history()
        self._refresh_history()

    # ------------------------------------------------------------------
    # Models section
    # ------------------------------------------------------------------

    def _build_models_section(self) -> None:
        _, layout = self._make_section_page()
        layout.addWidget(_section_title("Models"))

        self._cache_size_label = QLabel("")
        self._cache_size_label.setFont(sans(12))
        self._cache_size_label.setStyleSheet(f"color: {LT_TEXT_SEC};")
        layout.addWidget(self._cache_size_label)

        layout.addSpacing(8)

        self._models_container = QVBoxLayout()
        self._models_container.setSpacing(8)
        layout.addLayout(self._models_container)

        self._refresh_models()
        layout.addStretch()

    def _refresh_models(self) -> None:
        while self._models_container.count():
            item = self._models_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        from keysay.models import list_cached_models, get_cache_size_gb

        total = get_cache_size_gb()
        self._cache_size_label.setText(f"Total cache: {total:.1f} GB")

        models = list_cached_models()

        if not models:
            empty = QLabel("No models downloaded")
            empty.setFont(sans(12))
            empty.setStyleSheet(f"color: {LT_TEXT_MUTED};")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._models_container.addWidget(empty)
            return

        active_ids = {
            self._config.model_id,
            self._config.vlm_model,
            self._config.correction_model,
        }

        for model in models:
            card = self._model_cache_card(model, model["repo_id"] in active_ids)
            self._models_container.addWidget(card)

    def _model_cache_card(self, model: dict, in_use: bool) -> QFrame:
        card = _card()
        cl = QHBoxLayout(card)
        cl.setContentsMargins(12, 10, 12, 10)
        cl.setSpacing(8)

        info = QVBoxLayout()
        info.setSpacing(2)

        name_label = QLabel(model["repo_id"])
        name_label.setFont(mono(11))
        name_label.setStyleSheet(f"color: {LT_TEXT}; background: transparent; border: none;")
        info.addWidget(name_label)

        size_text = f"{model['size_gb']:.1f} GB"
        if in_use:
            size_text += "  \u00b7  In use"
        size_label = QLabel(size_text)
        size_label.setFont(sans(10))
        color = LT_ACCENT if in_use else LT_TEXT_MUTED
        size_label.setStyleSheet(f"color: {color}; background: transparent; border: none;")
        info.addWidget(size_label)

        cl.addLayout(info, 1)

        del_btn = QPushButton("Delete")
        del_btn.setFont(sans(10))
        del_btn.setFixedHeight(26)
        del_btn.setEnabled(not in_use)
        if in_use:
            del_btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; color: {LT_TEXT_MUTED};
                    border: 1px solid {LT_BORDER}; border-radius: 6px; padding: 0 10px;
                }}
            """)
        else:
            del_btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; color: {LT_TEXT_SEC};
                    border: 1px solid {LT_BORDER}; border-radius: 6px; padding: 0 10px;
                }}
                QPushButton:hover {{ color: #ff6b6b; border-color: #ff6b6b; }}
            """)
        repo_id = model["repo_id"]
        del_btn.clicked.connect(lambda _, rid=repo_id: self._delete_model(rid))
        cl.addWidget(del_btn)

        return card

    def _delete_model(self, repo_id: str) -> None:
        from keysay.models import delete_cached_model
        if delete_cached_model(repo_id):
            self._refresh_models()

    # ------------------------------------------------------------------

    def _populate(self, cfg: Config) -> None:
        self._status_banner.set_active(cfg.active)
        # Mic device
        mic_idx = 0  # default
        for i in range(self._mic_combo.count()):
            if self._mic_combo.itemData(i) == cfg.mic_device:
                mic_idx = i
                break
        self._mic_combo.setCurrentIndex(mic_idx)
        idx = SUPPORTED_LANGUAGES.index(cfg.language) if cfg.language in SUPPORTED_LANGUAGES else 0
        self._language_combo.setCurrentIndex(idx)
        preset_names = [p[0] for p in HOTKEY_PRESETS]
        if cfg.hotkey_name in preset_names:
            self._hotkey_combo.setCurrentIndex(preset_names.index(cfg.hotkey_name))
        model_ids = [m[0] for m in SUPPORTED_MODELS]
        midx = model_ids.index(cfg.model_id) if cfg.model_id in model_ids else 0
        self._model_combo.setCurrentIndex(midx)
        quant_ids = [q[0] for q in SUPPORTED_QUANTIZATIONS]
        qidx = quant_ids.index(cfg.quantization) if cfg.quantization in quant_ids else 0
        self._quant_combo.setCurrentIndex(qidx)
        self._vlm_toggle.set_on(cfg.vlm_enabled)
        vlm_model_ids = [m[0] for m in VLM_MODELS]
        vidx = vlm_model_ids.index(cfg.vlm_model) if cfg.vlm_model in vlm_model_ids else 0
        self._vlm_model_combo.setCurrentIndex(vidx)
        preset_keys = [k for k, _ in PRESET_CHOICES]
        pidx = preset_keys.index(cfg.correction_preset) if cfg.correction_preset in preset_keys else 0
        self._correction_preset_combo.setCurrentIndex(pidx)
        self._clipboard_fallback_toggle.set_on(cfg.clipboard_fallback)
        self._dynamic_loading_toggle.set_on(cfg.dynamic_loading)
        self._on_vlm_toggled()
        self._update_ram_bar()
        self._tag_input.set_tags(cfg.context_words)
        self._replacements.set_pairs(cfg.replacements)

    def _read_config(self) -> Config:
        hotkey_idx = self._hotkey_combo.currentIndex()
        hk_name, hk_keycode, hk_is_mod = HOTKEY_PRESETS[hotkey_idx]
        mic_data = self._mic_combo.currentData()
        return Config(
            active=self._status_banner.is_active(),
            language=self._language_combo.currentText(),
            mic_device=mic_data if mic_data is not None else -1,
            context_words=self._tag_input.get_tags(),
            replacements=self._replacements.get_pairs(),
            model_id=self._model_combo.currentData(),
            quantization=self._quant_combo.currentData(),
            hotkey_keycode=hk_keycode,
            hotkey_name=hk_name,
            hotkey_is_modifier=hk_is_mod,
            pill_x=self._config.pill_x,
            pill_y=self._config.pill_y,
            vlm_enabled=self._vlm_toggle.is_on(),
            vlm_model=self._vlm_model_combo.currentData(),
            correction_preset=self._correction_preset_combo.currentData(),
            clipboard_fallback=self._clipboard_fallback_toggle.is_on(),
            dynamic_loading=self._dynamic_loading_toggle.is_on(),
        )

    def _update_dynamic_loading_ui(self) -> None:
        """Show/hide status banner based on dynamic loading state."""
        dynamic = self._dynamic_loading_toggle.is_on()
        self._status_banner.setVisible(not dynamic)

    def _on_vlm_toggled(self) -> None:
        enabled = self._vlm_toggle.is_on()
        self._vlm_model_combo.setEnabled(enabled)
        self._update_ram_bar()

    def _update_ram_bar(self) -> None:
        """Update all RAM-related labels and the bottom status bar."""
        if self._populating:
            return

        # ASR RAM
        asr_model = self._model_combo.currentData() or ""
        asr_ram = ASR_RAM_ESTIMATES.get(asr_model, 0)
        self._asr_ram_label.setText(f"~{asr_ram:.1f} GB")

        # VLM RAM
        vlm_idx = self._vlm_model_combo.currentIndex()
        vlm_ram = VLM_MODELS[vlm_idx][2] if 0 <= vlm_idx < len(VLM_MODELS) else 0
        if self._vlm_toggle.is_on():
            self._vlm_ram_label.setText(f"~{vlm_ram:.1f} GB")
        else:
            vlm_ram = 0
            self._vlm_ram_label.setText("Disabled")

        # Correction model info + RAM
        correction_key = self._correction_preset_combo.currentData()
        correction_ram = 0.0
        if correction_key and correction_key != "none":
            correction_ram = CORRECTION_RAM_ESTIMATE
            self._correction_model_label.setText(
                f"{self._config.correction_model}\n~{correction_ram:.1f} GB"
            )
            self._edit_prompt_btn.setEnabled(True)
        else:
            self._correction_model_label.setText("Disabled")
            self._edit_prompt_btn.setEnabled(False)

        # Per-model segments — show actual loaded state
        dynamic = self._dynamic_loading_toggle.is_on()
        active = self._status_banner.is_active()
        if dynamic:
            # Dynamic loading: show based on what's actually loaded right now
            segments = []
            if self._models_loaded.get("asr"):
                segments.append(("ASR", asr_ram, "#5ac8fa"))
            if self._models_loaded.get("vlm") and vlm_ram > 0:
                segments.append(("VLM", vlm_ram, "#34c759"))
            if self._models_loaded.get("corrector") and correction_ram > 0:
                segments.append(("Post", correction_ram, "#f5a623"))
        elif active:
            segments = [("ASR", asr_ram, "#5ac8fa")]
            if vlm_ram > 0:
                segments.append(("VLM", vlm_ram, "#34c759"))
            if correction_ram > 0:
                segments.append(("Post", correction_ram, "#f5a623"))
        else:
            segments = []
        self._ram_bar.set_segments(segments)

    def _edit_prompt(self) -> None:
        from keysay.llm.presets import CORRECTION_PRESETS
        key = self._correction_preset_combo.currentData()
        if key == "none":
            return
        preset = CORRECTION_PRESETS.get(key)
        if not preset:
            return
        current = self._config.custom_prompts.get(key, preset["system"])
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Edit: {preset['label']}")
        dlg.setMinimumSize(540, 400)
        dlg.setStyleSheet(light_dialog_qss())
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)
        editor = QPlainTextEdit()
        editor.setPlainText(current)
        editor.setFont(mono(12))
        layout.addWidget(editor)
        br = QHBoxLayout()
        br.addStretch()
        rb = QPushButton("Reset")
        rb.setObjectName("ghostBtn")
        cb = QPushButton("Cancel")
        cb.setObjectName("ghostBtn")
        sb = QPushButton("Save")
        sb.setObjectName("accentBtn")
        sb.setDefault(True)
        br.addWidget(rb)
        br.addWidget(cb)
        br.addWidget(sb)
        layout.addLayout(br)
        rb.clicked.connect(lambda: editor.setPlainText(preset["system"]))
        cb.clicked.connect(dlg.reject)

        def _save():
            text = editor.toPlainText().strip()
            if text == preset["system"]:
                self._config.custom_prompts.pop(key, None)
            else:
                self._config.custom_prompts[key] = text
            dlg.accept()
            self._auto_save()

        sb.clicked.connect(_save)
        dlg.exec()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        # Prevent Enter/Return from closing the dialog (QDialog default behavior)
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            # Let focused widget handle it (e.g. QLineEdit returnPressed)
            focused = self.focusWidget()
            if focused and isinstance(focused, QLineEdit):
                focused.returnPressed.emit()
            return
        super().keyPressEvent(event)

    def _on_quit(self) -> None:
        self.quit_requested.emit()
        self.reject()
