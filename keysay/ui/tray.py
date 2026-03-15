"""System tray icon — flat coral dot, dark menu."""

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon, QWidget

from keysay.ui.theme import (
    BG_CARD, BG_HOVER, BORDER_SUBTLE, CORAL,
    STATE_INACTIVE, TEXT_PRIMARY, TEXT_MUTED,
    sans,
)


def _make_icon(active: bool) -> QIcon:
    size = 22
    pm = QPixmap(QSize(size, size))
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    color = QColor(CORAL) if active else QColor(STATE_INACTIVE)
    p.setBrush(color)
    dot = 10
    offset = (size - dot) // 2
    p.drawEllipse(offset, offset, dot, dot)
    p.end()
    return QIcon(pm)


class TrayIcon(QSystemTrayIcon):
    open_settings = pyqtSignal()
    toggle_active = pyqtSignal(bool)
    quit_app = pyqtSignal()

    def __init__(self, active: bool = True, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._active = active
        self.setIcon(_make_icon(active))
        self.setToolTip("keysay")
        self._build_menu()

    def _build_menu(self) -> None:
        menu = QMenu()
        menu.setFont(sans(13))
        menu.setStyleSheet(f"""
            QMenu {{
                background: {BG_CARD};
                color: {TEXT_PRIMARY};
                border: 1px solid {BORDER_SUBTLE};
                border-radius: 8px;
                padding: 4px 0;
            }}
            QMenu::item {{ padding: 6px 24px; }}
            QMenu::item:selected {{ background: {BG_HOVER}; }}
            QMenu::separator {{
                height: 1px; background: {BORDER_SUBTLE}; margin: 4px 12px;
            }}
        """)

        self._settings_action = QAction("Settings...")
        self._settings_action.triggered.connect(self.open_settings.emit)
        menu.addAction(self._settings_action)
        menu.addSeparator()

        self._toggle_action = QAction(self._toggle_text())
        self._toggle_action.triggered.connect(self._on_toggle)
        menu.addAction(self._toggle_action)
        menu.addSeparator()

        self._quit_action = QAction("Quit")
        self._quit_action.triggered.connect(self.quit_app.emit)
        menu.addAction(self._quit_action)

        self.setContextMenu(menu)

    def set_active(self, active: bool) -> None:
        self._active = active
        self.setIcon(_make_icon(active))
        self._toggle_action.setText(self._toggle_text())

    def _toggle_text(self) -> str:
        return "Deactivate" if self._active else "Activate"

    def _on_toggle(self) -> None:
        self._active = not self._active
        self.set_active(self._active)
        self.toggle_active.emit(self._active)
