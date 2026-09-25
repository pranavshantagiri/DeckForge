"""DeckForge desktop GUI (PySide6). Thin layer; all logic in deckforge_core.

Launch with ``deckforge-gui`` (or ``python -m deckforge_core.gui.main``).
Screens: packs home, generate, settings.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication, QMainWindow, QTabWidget, QWidget

from deckforge_core import __version__
from deckforge_core.config import SecretStore, Settings, ensure_dirs
from deckforge_core.gui import models
from deckforge_core.gui.generate_page import GeneratePage
from deckforge_core.gui.packs_page import PacksPage
from deckforge_core.gui.settings_page import SettingsPage
from deckforge_core.gui.style import apply_theme
from deckforge_core.logging_util import get_logger

log = get_logger("deckforge.gui")

PACKS_TAB = 0
GENERATE_TAB = 1
SETTINGS_TAB = 2


class MainWindow(QMainWindow):
    """The whole application: three tabs over one shared settings store."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        secrets: Optional[SecretStore] = None,
        packs_dir: Optional[Path] = None,
        decks_dir: Optional[Path] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.settings = settings or Settings()
        self.secrets = secrets or SecretStore()
        self.packs_dir = models.packs_root(packs_dir)
        self.packs_dir.mkdir(parents=True, exist_ok=True)

        self.setWindowTitle(f"DeckForge {__version__}")
        self.resize(1180, 780)

        self.tabs = QTabWidget()
        self.packs_page = PacksPage(self.packs_dir)
        self.generate_page = GeneratePage(self.packs_dir, self.settings, decks_dir)
        self.settings_page = SettingsPage(self.settings, self.secrets)
        self.tabs.addTab(self.packs_page, "Packs")
        self.tabs.addTab(self.generate_page, "Generate")
        self.tabs.addTab(self.settings_page, "Settings")
        self.setCentralWidget(self.tabs)

        self.packs_page.pack_chosen.connect(self._on_pack_chosen)
        self.packs_page.packs_changed.connect(self.generate_page.refresh_packs)
        self.settings_page.settings_saved.connect(self._on_settings_saved)
        self._status = self.statusBar()
        self.say(
            f"Packs: {self.packs_dir}  ·  slide renderers: "
            f"{', '.join(models.available_render_backends())}"
        )

    # --- navigation ---
    def show_tab(self, index: int) -> None:
        self.tabs.setCurrentIndex(index)
        if index == PACKS_TAB:
            self.packs_page.refresh()
        elif index == GENERATE_TAB:
            self.generate_page.refresh_packs()

    def refresh_all(self) -> None:
        self.packs_page.refresh()
        self.generate_page.refresh_packs()

    def say(self, message: str) -> None:
        self._status.showMessage(message)

    @property
    def busy(self) -> bool:
        return self.packs_page.runner.busy or self.generate_page.runner.busy

    def closeEvent(self, event: QEvent) -> None:  # noqa: N802 - Qt naming
        if self.busy:
            self.say("Still working — the window stays open until the task finishes.")
            event.ignore()
            return
        super().closeEvent(event)

    # --- signals ---
    def _on_pack_chosen(self, name: str) -> None:
        if self.generate_page.select_pack(name):
            self.show_tab(GENERATE_TAB)
            self.say(f"Pack '{name}' selected for the next deck")

    def _on_settings_saved(self) -> None:
        self.generate_page.settings = self.settings
        self.say("Settings saved")


def build_app(argv: Optional[list[str]] = None) -> tuple[QApplication, MainWindow]:
    """Create the themed application and its main window without showing it."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(list(argv) if argv is not None else sys.argv)
    app.setApplicationName("DeckForge")
    app.setOrganizationName("DeckForge")
    app.setApplicationVersion(__version__)
    apply_theme(app)
    return app, MainWindow()


def main() -> None:
    ensure_dirs()
    app, window = build_app()
    window.show()
    log.info("DeckForge GUI started; packs in %s", window.packs_dir)
    raise SystemExit(app.exec())


if __name__ == "__main__":  # pragma: no cover
    main()
