"""Generate screen: brief in, native .pptx out, with slide previews."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from deckforge_core.config import Settings
from deckforge_core.gui import models
from deckforge_core.gui.style import hint_label, muted_label, title_label
from deckforge_core.gui.workers import TaskRunner
from deckforge_core.logging_util import get_logger

log = get_logger("deckforge.gui.generate")

_ROLE = Qt.ItemDataRole.UserRole
_THUMB = QSize(208, 117)


class GeneratePage(QWidget):
    """Pick a pack, write a brief, render a deck, inspect and open it."""

    def __init__(
        self,
        packs_dir: Optional[Path] = None,
        settings: Optional[Settings] = None,
        decks_dir: Optional[Path] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.packs_dir = models.packs_root(packs_dir)
        self.decks_dir = Path(decks_dir) if decks_dir is not None else None
        self.settings = settings or Settings()
        self.runner = TaskRunner(self)
        self._result: Optional[models.GenerationResult] = None

        self.title = title_label("Generate a deck")

        self.pack_combo = QComboBox()
        self.pack_combo.setToolTip("Format Pack the deck is styled and laid out with")
        self.brief_edit = QPlainTextEdit()
        self.brief_edit.setPlaceholderText(
            "e.g. Q3 results for the leadership team: growth, churn drivers, plan"
        )
        self.brief_edit.setMinimumHeight(90)
        self.audience_edit = QLineEdit()
        self.audience_edit.setPlaceholderText("e.g. exec staff, customers, engineers")
        self.slide_count = QSpinBox()
        self.slide_count.setRange(3, 40)
        self.slide_count.setValue(10)
        self.tone_combo = QComboBox()
        self.tone_combo.addItems(list(models.TONES))
        self.aspect_combo = QComboBox()
        for ratio in models.ASPECT_RATIOS:
            self.aspect_combo.addItem(ratio, ratio)
        self.aspect_combo.setCurrentIndex(0)
        self.backend_combo = QComboBox()
        for backend in ("auto", "none", *models.available_render_backends()):
            label = {
                "auto": "auto (best available)",
                "none": "none (no preview images)",
            }.get(backend, backend)
            self.backend_combo.addItem(label, backend)

        self.offline_radio = QRadioButton("Rule-based plan (offline, deterministic)")
        self.offline_radio.setChecked(True)
        self.llm_radio = QRadioButton("LLM plan (uses your configured provider)")
        self.provider_combo = QComboBox()
        for provider in models.available_llm_providers():
            self.provider_combo.addItem(provider, provider)
        current_provider = str(self.settings.get("llm_provider") or "")
        index = self.provider_combo.findData(current_provider)
        if index >= 0:
            self.provider_combo.setCurrentIndex(index)
        self.llm_radio.toggled.connect(self.provider_combo.setEnabled)
        self.provider_combo.setEnabled(False)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.addRow("Format pack", self.pack_combo)
        form.addRow("Deck brief", self.brief_edit)
        form.addRow("Audience", self.audience_edit)
        form.addRow("Slides", self.slide_count)
        form.addRow("Tone", self.tone_combo)
        form.addRow("Aspect ratio", self.aspect_combo)
        form.addRow("Planner", self.offline_radio)
        form.addRow("", self.llm_radio)
        form.addRow("Provider", self.provider_combo)
        form.addRow("Slide previews", self.backend_combo)

        self.generate_button = QPushButton("Generate deck")
        self.generate_button.setObjectName("Primary")
        self.generate_button.clicked.connect(self.on_generate_clicked)
        self.open_button = QPushButton("Open in PowerPoint")
        self.open_button.clicked.connect(self.on_open_clicked)
        self.reveal_button = QPushButton("Show in folder")
        self.reveal_button.clicked.connect(self.on_reveal_clicked)
        self.preview_button = QPushButton("Render previews")
        self.preview_button.clicked.connect(self.on_preview_clicked)
        self.open_button.setEnabled(False)
        self.reveal_button.setEnabled(False)
        self.preview_button.setEnabled(False)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setVisible(False)
        self.status = QLabel("")
        self.status.setObjectName("Muted")
        self.status.setWordWrap(True)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)
        left_layout.addWidget(
            hint_label(
                "The planner fills slots only; colours, fonts and geometry come "
                "from the pack, so the output stays native and editable."
            )
        )
        left_layout.addLayout(form)
        left_layout.addStretch(1)
        left_layout.addWidget(self.progress)
        left_layout.addWidget(self.status)
        left.setMinimumWidth(380)

        self.thumb_list = QListWidget()
        self.thumb_list.setViewMode(QListWidget.ViewMode.IconMode)
        self.thumb_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.thumb_list.setMovement(QListWidget.Movement.Static)
        self.thumb_list.setIconSize(_THUMB)
        self.thumb_list.setGridSize(QSize(_THUMB.width() + 28, _THUMB.height() + 34))
        self.thumb_list.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.thumb_list.setWordWrap(False)
        self.thumb_list.currentItemChanged.connect(self._on_thumb_changed)

        self.stage = QLabel("No deck generated yet.")
        self.stage.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.stage.setFrameShape(QFrame.Shape.StyledPanel)
        self.stage.setMinimumHeight(300)
        self.stage.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.stage.setStyleSheet("background: #FFFFFF; color: #6B6B66;")

        self.issues_list = QListWidget()
        self.issues_list.setMaximumHeight(140)

        preview_column = QWidget()
        preview_layout = QVBoxLayout(preview_column)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(8)
        preview_layout.addWidget(muted_label("Preview"), 0)
        preview_layout.addWidget(self.stage, 1)
        preview_layout.addWidget(self.thumb_list, 1)
        preview_layout.addWidget(muted_label("QA findings"), 0)
        preview_layout.addWidget(self.issues_list)

        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.addWidget(self.generate_button)
        buttons.addWidget(self.open_button)
        buttons.addWidget(self.reveal_button)
        buttons.addWidget(self.preview_button)
        buttons.addStretch(1)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left)
        splitter.addWidget(preview_column)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setChildrenCollapsible(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)
        layout.addWidget(self.title)
        layout.addWidget(splitter, 1)
        layout.addLayout(buttons)

        self.refresh_packs()
        self._sync_buttons()

    # --- input state ---
    def refresh_packs(self) -> None:
        current = self.pack_combo.currentData()
        self.pack_combo.clear()
        for entry in models.list_pack_entries(self.packs_dir):
            self.pack_combo.addItem(entry.name, str(entry.path))
        index = self.pack_combo.findData(current)
        if index >= 0:
            self.pack_combo.setCurrentIndex(index)
        if not self.pack_combo.count():
            self.status.setText("No format packs yet — learn one on the Packs tab.")

    def select_pack(self, name: str) -> bool:
        for index in range(self.pack_combo.count()):
            if self.pack_combo.itemText(index) == name:
                self.pack_combo.setCurrentIndex(index)
                return True
        return False

    def current_pack_dir(self) -> Optional[Path]:
        data = self.pack_combo.currentData()
        return Path(data) if data else None

    def build_request(self) -> models.GenerationRequest:
        pack_dir = self.current_pack_dir()
        if pack_dir is None:
            raise ValueError("select a format pack first")
        return models.GenerationRequest(
            pack_dir=pack_dir,
            brief=self.brief_edit.toPlainText().strip(),
            slide_count=self.slide_count.value(),
            tone=self.tone_combo.currentText(),
            audience=self.audience_edit.text().strip(),
            aspect_ratio=str(self.aspect_combo.currentData() or "16:9"),
            use_llm=self.llm_radio.isChecked(),
            llm_provider=str(self.provider_combo.currentData() or ""),
            render_backend=str(self.backend_combo.currentData() or "auto"),
            out_dir=models.new_deck_dir(
                self.brief_edit.toPlainText().strip(), self.decks_dir
            ),
        )

    # --- work ---
    def run_generation(
        self,
        *,
        progress: Optional[models.ProgressFn] = None,
    ) -> models.GenerationResult:
        return models.generate(
            self.build_request(), progress=progress, settings=self.settings
        )

    def start_generation(self) -> bool:
        self.progress.setValue(0)
        self.progress.setVisible(True)
        self.status.setText("Working…")
        started = self.runner.start(
            self.run_generation,
            on_progress=self._on_progress,
            on_success=self.show_result,
            on_error=self._on_failed,
        )
        if not started:
            self.progress.setVisible(False)
            self.status.setText("Already busy — wait for the current deck to finish.")
        return started

    def show_result(self, result: models.GenerationResult) -> None:
        self._result = result
        self.progress.setValue(100)
        self.progress.setVisible(False)
        self.thumb_list.clear()
        for preview in result.previews:
            item = QListWidgetItem(preview.label)
            item.setData(_ROLE, preview.number)
            item.setToolTip(preview.title or preview.archetype)
            if preview.image_path:
                item.setIcon(self._pixmap(preview.image_path, _THUMB))
            self.thumb_list.addItem(item)
        self._populate_issues(result)
        if self.thumb_list.count():
            self.thumb_list.setCurrentRow(0)
        else:
            self.stage.setText("No slides in this deck.")
        self.status.setText(self._summary(result))
        self._sync_buttons()
        log.info("generated %s (%d slides)", result.pptx_path, result.slide_count)

    def repreview(self) -> models.GenerationResult:
        if self._result is None:
            raise ValueError("generate a deck first")
        backend, images, notes = models.render_slide_previews(
            self._result.pptx_path,
            self._result.pptx_path.parent / "renders",
            str(self.backend_combo.currentData() or "auto"),
        )
        self._result.backend = backend
        self._result.warnings.extend(notes)
        for preview in self._result.previews:
            preview.image_path = images.get(preview.number, "")
        self.show_result(self._result)
        return self._result

    def current_pptx(self) -> Optional[Path]:
        return self._result.pptx_path if self._result else None

    # --- actions ---
    def on_generate_clicked(self) -> None:
        try:
            self.build_request()
        except ValueError as exc:
            self._on_failed(str(exc))
            return
        self.start_generation()

    def on_open_clicked(self) -> None:
        path = self.current_pptx()
        if path is None:
            return
        try:
            models.open_in_default_app(path)
        except Exception as exc:
            self._on_failed(str(exc))
            return
        self.status.setText(f"Opened {path.name} in PowerPoint")

    def on_reveal_clicked(self) -> None:
        path = self.current_pptx()
        if path is None:
            return
        try:
            models.reveal_in_file_manager(path)
        except Exception as exc:
            self._on_failed(str(exc))

    def on_preview_clicked(self) -> None:
        try:
            self.repreview()
        except Exception as exc:
            self._on_failed(str(exc))

    def show_error(self, message: str) -> None:
        QMessageBox.warning(self, "DeckForge", message)

    # --- internals ---
    def _summary(self, result: models.GenerationResult) -> str:
        parts = [f"{result.slide_count} slides → {result.pptx_path.name}"]
        if result.rendered_previews:
            parts.append(f"{result.rendered_previews} previews via {result.backend}")
        else:
            parts.append("no previews (install PowerPoint or LibreOffice)")
        if result.qa is not None:
            parts.append(
                f"QA: {result.errors_total} errors, {result.warnings_total} warnings"
            )
        return " · ".join(parts)

    def _populate_issues(self, result: models.GenerationResult) -> None:
        self.issues_list.clear()
        for preview in result.previews:
            for issue in preview.issues:
                self.issues_list.addItem(f"slide {preview.number}: {issue}")
        if not self.issues_list.count() and result.qa is not None:
            self.issues_list.addItem("No QA findings.")

    def _pixmap(self, image_path: str, size: QSize) -> QPixmap:
        pixmap = QPixmap(str(image_path))
        if pixmap.isNull():
            return QPixmap()
        return pixmap.scaled(
            size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

    def _on_thumb_changed(self, current: Optional[QListWidgetItem], _previous=None) -> None:
        if current is None or self._result is None:
            return
        number = int(current.data(_ROLE))
        preview = next(
            (item for item in self._result.previews if item.number == number), None
        )
        if preview is None:
            return
        if preview.image_path:
            self.stage.setPixmap(self._pixmap(preview.image_path, self.stage.size()))
            self.stage.setToolTip(str(Path(preview.image_path)))
            return
        self.stage.setPixmap(QPixmap())
        self.stage.setText(
            f"Slide {preview.number} — {preview.archetype}\n\n"
            f"{preview.title or '(no title)'}\n\nNo preview image for this slide."
        )
        self.stage.setToolTip("")

    def _on_progress(self, percent: int, message: str) -> None:
        if percent >= 0:
            self.progress.setValue(min(100, percent))
        self.status.setText(message)

    def _on_failed(self, message: str) -> None:
        self.progress.setVisible(False)
        self.status.setText(f"Failed: {message}")
        log.warning("generate page task failed: %s", message)
        self.show_error(message)

    def _sync_buttons(self) -> None:
        has_result = self._result is not None
        self.open_button.setEnabled(has_result)
        self.reveal_button.setEnabled(has_result)
        self.preview_button.setEnabled(has_result)
        self.generate_button.setEnabled(self.pack_combo.count() > 0)
