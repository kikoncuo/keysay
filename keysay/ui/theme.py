"""Keysay theme — warm dark, soft blue accent, macOS-native feel."""

import os
from PyQt6.QtGui import QColor, QFontDatabase, QFont

_FONT_DIR = os.path.join(os.path.dirname(__file__), "fonts")

# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------

# Surfaces
BG_WINDOW = "#1c1c1e"
BG_CARD = "#2c2c2e"
BG_INPUT = "#3a3a3c"
BG_HOVER = "#48484a"

# Borders
BORDER_SUBTLE = "#3a3a3c"
BORDER_DEFAULT = "#545458"

# Text
TEXT_PRIMARY = "#f5f5f7"
TEXT_SECONDARY = "#aeaeb2"
TEXT_MUTED = "#636366"

# Accent — soft sky blue (iOS system blue)
ACCENT = "#5ac8fa"
ACCENT_DIM = "#1a3040"
ACCENT_HOVER = "#7ad4fc"

# Compat aliases — old name → new (so pill/tray/permissions don't break)
CORAL = ACCENT
CORAL_DIM = ACCENT_DIM
CORAL_HOVER = ACCENT_HOVER

# State
STATE_ACTIVE = "#34c759"
STATE_INACTIVE = "#636366"

# QColor instances
Q_VOID = QColor(28, 28, 30, 230)
Q_SHADOW = QColor(0, 0, 0, 80)
Q_CORAL = QColor(ACCENT)          # compat alias
Q_CORAL_DIM = QColor(90, 200, 250, 30)
Q_ACCENT = QColor(ACCENT)
Q_ACCENT_DIM = QColor(90, 200, 250, 30)
Q_TEXT = QColor(TEXT_PRIMARY)
Q_TEXT_SEC = QColor(TEXT_SECONDARY)
Q_BORDER = QColor(BORDER_SUBTLE)
Q_BORDER_DEF = QColor(BORDER_DEFAULT)

# ---------------------------------------------------------------------------
# Font loading
# ---------------------------------------------------------------------------

_fonts_loaded = False
_mono_family = "DM Mono"
_sans_family = "DM Sans"


def load_fonts() -> None:
    global _fonts_loaded, _mono_family, _sans_family
    if _fonts_loaded:
        return
    _fonts_loaded = True

    for fname in (
        "DMMono-Regular.ttf", "DMMono-Medium.ttf",
        "DMSans-Regular.ttf", "DMSans-Medium.ttf", "DMSans-SemiBold.ttf",
    ):
        path = os.path.join(_FONT_DIR, fname)
        if os.path.exists(path):
            fid = QFontDatabase.addApplicationFont(path)
            if fid >= 0:
                families = QFontDatabase.applicationFontFamilies(fid)
                if families:
                    if "Mono" in fname:
                        _mono_family = families[0]
                    else:
                        _sans_family = families[0]

    all_fams = QFontDatabase.families()
    if _mono_family not in all_fams:
        for fb in ("SF Mono", "Menlo", "Courier New"):
            if fb in all_fams:
                _mono_family = fb
                break
    if _sans_family not in all_fams:
        for fb in ("SF Pro Display", "Helvetica Neue", "Helvetica"):
            if fb in all_fams:
                _sans_family = fb
                break


def mono(size: int = 13, medium: bool = False) -> QFont:
    load_fonts()
    f = QFont(_mono_family, size)
    if medium:
        f.setWeight(QFont.Weight.Medium)
    f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.3)
    return f


def sans(size: int = 13, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    load_fonts()
    f = QFont(_sans_family, size)
    f.setWeight(weight)
    return f


# ---------------------------------------------------------------------------
# QSS
# ---------------------------------------------------------------------------

def dialog_qss() -> str:
    return f"""
        QDialog {{
            background-color: {BG_WINDOW};
            color: {TEXT_PRIMARY};
        }}
        QLabel {{
            color: {TEXT_PRIMARY};
            background: transparent;
        }}
        QComboBox {{
            background: {BG_INPUT};
            color: {TEXT_PRIMARY};
            border: 1px solid {BORDER_SUBTLE};
            border-radius: 8px;
            padding: 6px 10px;
            min-height: 20px;
        }}
        QComboBox:focus {{ border-color: {ACCENT}; }}
        QComboBox:hover {{ border-color: {BORDER_DEFAULT}; }}
        QComboBox::drop-down {{ border: none; width: 24px; }}
        QComboBox::down-arrow {{
            image: none;
            border-left: 4px solid transparent;
            border-right: 4px solid transparent;
            border-top: 5px solid {TEXT_MUTED};
            margin-right: 6px;
        }}
        QComboBox QAbstractItemView {{
            background: {BG_CARD};
            color: {TEXT_PRIMARY};
            border: 1px solid {BORDER_SUBTLE};
            selection-background-color: {BG_HOVER};
            selection-color: {TEXT_PRIMARY};
            outline: none;
            padding: 2px;
        }}
        QLineEdit {{
            background: {BG_INPUT};
            color: {TEXT_PRIMARY};
            border: 1px solid {BORDER_SUBTLE};
            border-radius: 8px;
            padding: 6px 10px;
        }}
        QLineEdit:focus {{ border-color: {ACCENT}; }}
        QLineEdit::placeholder {{ color: {TEXT_MUTED}; }}
        QPlainTextEdit {{
            background: {BG_INPUT};
            color: {TEXT_PRIMARY};
            border: 1px solid {BORDER_SUBTLE};
            border-radius: 8px;
            padding: 8px;
        }}
        QPlainTextEdit:focus {{ border-color: {ACCENT}; }}
        QPushButton {{
            background: {BG_CARD};
            color: {TEXT_PRIMARY};
            border: 1px solid {BORDER_SUBTLE};
            border-radius: 8px;
            padding: 7px 18px;
        }}
        QPushButton:hover {{ background: {BG_HOVER}; border-color: {BORDER_DEFAULT}; }}
        QPushButton:pressed {{ background: {BG_INPUT}; }}
        QPushButton#accentBtn {{
            background: {ACCENT};
            color: #1c1c1e;
            border: none;
            font-weight: 600;
        }}
        QPushButton#accentBtn:hover {{ background: {ACCENT_HOVER}; }}
        QPushButton#ghostBtn {{
            background: transparent;
            border: 1px solid {BORDER_SUBTLE};
            color: {TEXT_SECONDARY};
        }}
        QPushButton#ghostBtn:hover {{ border-color: {TEXT_PRIMARY}; color: {TEXT_PRIMARY}; }}
        QScrollArea {{ background: transparent; border: none; }}
        QScrollArea > QWidget > QWidget {{ background: transparent; }}
        QScrollBar:vertical {{ background: transparent; width: 6px; border: none; }}
        QScrollBar::handle:vertical {{
            background: {BORDER_DEFAULT}; border-radius: 3px; min-height: 30px;
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    """


# ---------------------------------------------------------------------------
# Light palette (for settings / dialogs — Wispr-inspired warm cream)
# ---------------------------------------------------------------------------

LT_BG = "#faf8f5"
LT_BG_SIDEBAR = "#f2efe9"
LT_CARD = "#ffffff"
LT_BORDER = "#e5e0d8"
LT_BORDER_HOVER = "#ccc7be"
LT_TEXT = "#1a1a1a"
LT_TEXT_SEC = "#6b6560"
LT_TEXT_MUTED = "#a09a93"
LT_INPUT_BG = "#f5f3ef"
LT_HOVER = "#edeae4"
LT_ACCENT = ACCENT  # keep same soft blue

Q_LT_BG = QColor(LT_BG)
Q_LT_CARD = QColor(LT_CARD)
Q_LT_BORDER = QColor(LT_BORDER)
Q_LT_TEXT = QColor(LT_TEXT)
Q_LT_TEXT_SEC = QColor(LT_TEXT_SEC)


def light_dialog_qss() -> str:
    return f"""
        QDialog {{
            background-color: {LT_BG};
            color: {LT_TEXT};
        }}
        QLabel {{
            color: {LT_TEXT};
            background: transparent;
        }}
        QComboBox {{
            background: {LT_INPUT_BG};
            color: {LT_TEXT};
            border: 1px solid {LT_BORDER};
            border-radius: 8px;
            padding: 6px 10px;
            min-height: 20px;
            combobox-popup: 0;
        }}
        QComboBox:focus {{ border-color: {LT_ACCENT}; }}
        QComboBox:hover {{ border-color: {LT_BORDER_HOVER}; }}
        QComboBox::drop-down {{ border: none; width: 24px; }}
        QComboBox::down-arrow {{
            image: none;
            border-left: 4px solid transparent;
            border-right: 4px solid transparent;
            border-top: 5px solid {LT_TEXT_MUTED};
            margin-right: 6px;
        }}
        QComboBox QAbstractItemView {{
            background: {LT_CARD};
            color: {LT_TEXT};
            border: 1px solid {LT_BORDER};
            border-radius: 8px;
            selection-background-color: {LT_HOVER};
            selection-color: {LT_TEXT};
            outline: none;
            padding: 4px;
        }}
        QComboBox QAbstractItemView::item {{
            padding: 6px 10px;
            border-radius: 4px;
        }}
        QComboBox QAbstractItemView::item:selected {{
            background: {LT_HOVER};
        }}
        QLineEdit {{
            background: {LT_INPUT_BG};
            color: {LT_TEXT};
            border: 1px solid {LT_BORDER};
            border-radius: 8px;
            padding: 6px 10px;
        }}
        QLineEdit:focus {{ border-color: {LT_ACCENT}; }}
        QLineEdit::placeholder {{ color: {LT_TEXT_MUTED}; }}
        QPlainTextEdit {{
            background: {LT_INPUT_BG};
            color: {LT_TEXT};
            border: 1px solid {LT_BORDER};
            border-radius: 8px;
            padding: 8px;
        }}
        QPlainTextEdit:focus {{ border-color: {LT_ACCENT}; }}
        QPushButton {{
            background: {LT_CARD};
            color: {LT_TEXT};
            border: 1px solid {LT_BORDER};
            border-radius: 8px;
            padding: 7px 18px;
        }}
        QPushButton:hover {{ background: {LT_HOVER}; border-color: {LT_BORDER_HOVER}; }}
        QPushButton:pressed {{ background: {LT_INPUT_BG}; }}
        QPushButton#accentBtn {{
            background: {LT_ACCENT};
            color: #ffffff;
            border: none;
            font-weight: 600;
        }}
        QPushButton#accentBtn:hover {{ background: {ACCENT_HOVER}; }}
        QPushButton#ghostBtn {{
            background: transparent;
            border: 1px solid {LT_BORDER};
            color: {LT_TEXT_SEC};
        }}
        QPushButton#ghostBtn:hover {{ border-color: {LT_TEXT}; color: {LT_TEXT}; }}
        QScrollArea {{ background: transparent; border: none; }}
        QScrollArea > QWidget > QWidget {{ background: transparent; }}
        QScrollBar:vertical {{ background: transparent; width: 6px; border: none; }}
        QScrollBar::handle:vertical {{
            background: {LT_BORDER}; border-radius: 3px; min-height: 30px;
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    """
