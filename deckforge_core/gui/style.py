"""Plain, consistent styling for the DeckForge window.

One stylesheet plus a couple of helpers so every page uses the same spacing,
type ramp and neutral palette.
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication, QWidget

INK = "#1C1C1A"
MUTED = "#6B6B66"
LINE = "#D9D8D2"
SURFACE = "#FFFFFF"
CANVAS = "#F4F3EF"
ACCENT = "#2F6F8F"

STYLESHEET = f"""
QWidget {{
    color: {INK};
    font-size: 13px;
}}
QMainWindow, QDialog {{
    background: {CANVAS};
}}
QLabel#PageTitle {{
    font-size: 18px;
    font-weight: 600;
}}
QLabel#PageHint, QLabel#Muted {{
    color: {MUTED};
}}
QGroupBox {{
    border: 1px solid {LINE};
    border-radius: 6px;
    margin-top: 14px;
    padding: 10px 12px 12px 12px;
    background: {SURFACE};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: {MUTED};
}}
QPushButton {{
    background: {SURFACE};
    border: 1px solid {LINE};
    border-radius: 5px;
    padding: 6px 14px;
    min-height: 18px;
}}
QPushButton:hover {{
    border-color: {ACCENT};
}}
QPushButton:disabled {{
    color: #A9A8A2;
    background: #EFEEE9;
}}
QPushButton#Primary {{
    background: {ACCENT};
    border-color: {ACCENT};
    color: #FFFFFF;
    font-weight: 600;
}}
QPushButton#Primary:hover {{
    background: #28607B;
}}
QPushButton#Primary:disabled {{
    background: #B9C7CE;
    border-color: #B9C7CE;
}}
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QComboBox {{
    background: {SURFACE};
    border: 1px solid {LINE};
    border-radius: 5px;
    padding: 5px 8px;
    selection-background-color: {ACCENT};
}}
QListWidget, QTableWidget, QTreeWidget {{
    background: {SURFACE};
    border: 1px solid {LINE};
    border-radius: 6px;
    outline: none;
}}
QListWidget::item {{
    padding: 6px 8px;
    border-radius: 4px;
}}
QListWidget::item:selected {{
    background: #E4EEF3;
    color: {INK};
}}
QProgressBar {{
    border: 1px solid {LINE};
    border-radius: 5px;
    background: {SURFACE};
    text-align: center;
    min-height: 18px;
}}
QProgressBar::chunk {{
    background: {ACCENT};
    border-radius: 4px;
}}
QTabWidget::pane {{
    border: 1px solid {LINE};
    border-radius: 6px;
    background: {CANVAS};
    top: -1px;
}}
QTabBar::tab {{
    background: transparent;
    border: 1px solid transparent;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    padding: 7px 18px;
    color: {MUTED};
}}
QTabBar::tab:selected {{
    background: {SURFACE};
    border-color: {LINE};
    border-bottom-color: {SURFACE};
    color: {INK};
    font-weight: 600;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 12px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: #C9C8C2;
    border-radius: 5px;
    min-height: 24px;
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    height: 0;
    width: 0;
}}
QSplitter::handle {{
    background: {LINE};
}}
"""


def apply_theme(app: QApplication) -> None:
    """Apply the DeckForge look to the whole application."""
    app.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(CANVAS))
    palette.setColor(QPalette.WindowText, QColor(INK))
    palette.setColor(QPalette.Base, QColor(SURFACE))
    palette.setColor(QPalette.AlternateBase, QColor("#F7F6F2"))
    palette.setColor(QPalette.Text, QColor(INK))
    palette.setColor(QPalette.Button, QColor(SURFACE))
    palette.setColor(QPalette.ButtonText, QColor(INK))
    palette.setColor(QPalette.Highlight, QColor(ACCENT))
    palette.setColor(QPalette.HighlightedText, QColor("#FFFFFF"))
    palette.setColor(QPalette.ToolTipBase, QColor(SURFACE))
    palette.setColor(QPalette.ToolTipText, QColor(INK))
    palette.setColor(QPalette.Disabled, QPalette.Text, QColor("#A9A8A2"))
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor("#A9A8A2"))
    app.setPalette(palette)
    font = QFont(app.font())
    font.setPointSizeF(max(9.0, font.pointSizeF()))
    app.setFont(font)
    app.setStyleSheet(STYLESHEET)


def title_label(text: str) -> QWidget:
    from PySide6.QtWidgets import QLabel

    label = QLabel(text)
    label.setObjectName("PageTitle")
    return label


def hint_label(text: str) -> QWidget:
    from PySide6.QtWidgets import QLabel

    label = QLabel(text)
    label.setObjectName("PageHint")
    label.setWordWrap(True)
    return label


def muted_label(text: str) -> QWidget:
    from PySide6.QtWidgets import QLabel

    label = QLabel(text)
    label.setObjectName("Muted")
    label.setWordWrap(True)
    return label
