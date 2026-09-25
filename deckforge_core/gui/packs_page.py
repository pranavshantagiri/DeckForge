"""Packs home screen: what format packs exist, and how to learn a new one."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from deckforge_core.gui import models
from deckforge_core.gui.style import hint_label, title_label
from deckforge_core.gui.workers import TaskRunner
from deckforge_core.logging_util import get_logger

log = get_logger("deckforge.gui.packs")

_ROLE = Qt.ItemDataRole.UserRole


class LearnPackDialog(QDialog):
    """Folder of source decks plus the name to give the learned pack."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Learn a format pack")
        self.setMinimumWidth(520)

        self.folder_edit = QLineEdit()
        self.folder_edit.setPlaceholderText("Folder containing .pptx decks")
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Pack name (defaults to the folder name)")

        browse = QPushButton("Browse…")
        browse.clicked.connect(self.browse)

        folder_row = QHBoxLayout()
        folder_row.setContentsMargins(0, 0, 0, 0)
        folder_row.addWidget(self.folder_edit, 1)
        folder_row.addWidget(browse)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.addRow("Source folder", folder_row)
        form.addRow("Pack name", self.name_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(
            hint_label(
                "Every .pptx in the folder (recursively) is parsed, clustered and "
                "turned into a Format Pack. This takes seconds to minutes."
            )
        )
        layout.addLayout(form)
        layout.addWidget(buttons)

    def browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Choose a folder of .pptx decks", self.folder_edit.text()
        )
        if folder:
            self.folder_edit.setText(folder)
            if not self.name_edit.text().strip():
                self.name_edit.setText(Path(folder).name)

    def values(self) -> tuple[Path, str]:
        folder = Path(self.folder_edit.text().strip())
        return folder, self.name_edit.text().strip() or folder.name


class PacksPage(QWidget):
    """Lists saved packs and drives the learn / import / delete actions."""

    pack_chosen = Signal(str)
    packs_changed = Signal()

    def __init__(self, packs_dir: Optional[Path] = None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.packs_dir = models.packs_root(packs_dir)
        self.runner = TaskRunner(self)

        self.title = title_label("Format packs")
        self.hint = hint_label(
            f"A Format Pack holds the style and slide blueprints DeckForge learned "
            f"from a folder of real decks. Packs live in {self.packs_dir}."
        )

        self.list = QListWidget()
        self.list.setAlternatingRowColors(True)
        self.list.itemSelectionChanged.connect(self._on_selection)
        self.list.itemDoubleClicked.connect(lambda _item: self._use_pack())

        self.status = QLabel("")
        self.status.setObjectName("Muted")
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setVisible(False)

        self.learn_button = QPushButton("Learn pack…")
        self.learn_button.setObjectName("Primary")
        self.learn_button.clicked.connect(self.on_learn_clicked)
        self.use_button = QPushButton("Use for a new deck")
        self.use_button.clicked.connect(self._use_pack)
        self.import_button = QPushButton("Import .dfpack…")
        self.import_button.clicked.connect(self.on_import_clicked)
        self.delete_button = QPushButton("Delete")
        self.delete_button.clicked.connect(self.on_delete_clicked)
        self.reveal_button = QPushButton("Show folder")
        self.reveal_button.clicked.connect(self.on_reveal_clicked)
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.refresh)

        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.addWidget(self.learn_button)
        buttons.addWidget(self.use_button)
        buttons.addSpacing(12)
        buttons.addWidget(self.import_button)
        buttons.addWidget(self.delete_button)
        buttons.addWidget(self.reveal_button)
        buttons.addStretch(1)
        buttons.addWidget(self.refresh_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)
        layout.addWidget(self.title)
        layout.addWidget(self.hint)
        layout.addWidget(self.list, 1)
        layout.addLayout(buttons)
        layout.addWidget(self.progress)
        layout.addWidget(self.status)

        self.refresh()
        self._sync_buttons()

    # --- data ---
    def entries(self) -> list[models.PackEntry]:
        return models.list_pack_entries(self.packs_dir)

    def refresh(self) -> None:
        current = self.selected_name()
        self.list.clear()
        for entry in self.entries():
            item = QListWidgetItem(f"{entry.name}\n{entry.summary}")
            item.setData(_ROLE, str(entry.path))
            item.setToolTip(str(entry.path))
            self.list.addItem(item)
        if current and self.select(current):
            pass
        elif self.list.count():
            self.list.setCurrentRow(0)
        self.packs_changed.emit()
        if not self.list.count():
            self.status.setText("No packs yet — use “Learn pack…” to build one.")
        elif not self.status.text().startswith("Learned"):
            self.status.setText(f"{self.list.count()} pack(s) in {self.packs_dir}")
        self._sync_buttons()

    def select(self, name: str) -> bool:
        for index in range(self.list.count()):
            item = self.list.item(index)
            if item.text().splitlines()[0] == name:
                self.list.setCurrentItem(item)
                return True
        return False

    def selected_entry(self) -> Optional[models.PackEntry]:
        item = self.list.currentItem()
        if item is None:
            return None
        path = Path(item.data(_ROLE))
        for entry in self.entries():
            if entry.path == path:
                return entry
        return models.PackEntry(name=path.name, path=path)

    def selected_name(self) -> str:
        item = self.list.currentItem()
        return item.text().splitlines()[0] if item is not None else ""

    # --- actions ---
    def learn(
        self,
        folder: Path,
        name: str,
        *,
        progress: Optional[models.ProgressFn] = None,
    ) -> models.LearnPackResult:
        return models.learn_pack_from_folder(
            folder,
            name,
            target_dir=self.packs_dir / models.slugify(name, fallback="pack"),
            progress=progress,
        )

    def start_learn(self, folder: Path, name: str) -> bool:
        self.progress.setValue(0)
        self.progress.setVisible(True)
        self.status.setText(f"Learning '{name}' from {folder}…")
        started = self.runner.start(
            self.learn,
            folder,
            name,
            on_progress=self._on_progress,
            on_success=self._on_learned,
            on_error=self._on_failed,
        )
        if not started:
            self.progress.setVisible(False)
        return started

    def import_pack(self, zip_path: Path) -> models.PackEntry:
        return models.import_pack_zip(zip_path, self.packs_dir)

    def on_learn_clicked(self) -> None:
        dialog = LearnPackDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        folder, name = dialog.values()
        if not folder.is_dir():
            QMessageBox.warning(self, "Learn pack", f"{folder} is not a folder.")
            return
        self.start_learn(folder, name)

    def on_import_clicked(self) -> None:
        zip_path, _ = QFileDialog.getOpenFileName(
            self, "Import a format pack", "", "Format packs (*.dfpack *.zip)"
        )
        if not zip_path:
            return
        try:
            entry = self.import_pack(Path(zip_path))
        except Exception as exc:
            self._on_failed(str(exc))
            return
        self.refresh()
        self.select(entry.name)
        self.status.setText(f"Imported '{entry.name}' into {entry.path}")

    def on_delete_clicked(self) -> None:
        entry = self.selected_entry()
        if entry is None:
            return
        confirm = QMessageBox.question(
            self,
            "Delete pack",
            f"Delete the pack '{entry.name}' and everything in {entry.path}?",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        shutil.rmtree(entry.path, ignore_errors=True)
        self.refresh()
        self.status.setText(f"Deleted '{entry.name}'")

    def on_reveal_clicked(self) -> None:
        entry = self.selected_entry()
        target = entry.path if entry is not None else self.packs_dir
        try:
            models.reveal_in_file_manager(target)
        except Exception as exc:
            self._on_failed(str(exc))

    # --- internals ---
    def show_error(self, message: str) -> None:
        QMessageBox.warning(self, "DeckForge", message)

    def _use_pack(self) -> None:
        name = self.selected_name()
        if name:
            self.pack_chosen.emit(name)

    def _on_selection(self) -> None:
        self._sync_buttons()

    def _sync_buttons(self) -> None:
        has_selection = self.list.currentItem() is not None
        self.use_button.setEnabled(has_selection)
        self.delete_button.setEnabled(has_selection)
        self.reveal_button.setEnabled(has_selection)

    def _on_progress(self, percent: int, message: str) -> None:
        if percent >= 0:
            self.progress.setValue(min(100, percent))
        self.status.setText(message)

    def _on_learned(self, result: models.LearnPackResult) -> None:
        self.progress.setValue(100)
        self.progress.setVisible(False)
        self.refresh()
        self.select(result.pack.name)
        details = f"Learned '{result.pack.name}' — {result.summary}"
        if result.ingest_errors:
            details += f" · {len(result.ingest_errors)} file(s) skipped"
        self.status.setText(details)
        log.info("learned pack %s", result.pack.name)

    def _on_failed(self, message: str) -> None:
        self.progress.setVisible(False)
        self.status.setText(f"Failed: {message}")
        log.warning("packs page task failed: %s", message)
        self.show_error(message)
