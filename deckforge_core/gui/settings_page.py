"""Settings screen: providers, models, render engine and API keys.

API keys are written to the OS credential store via :class:`SecretStore`; the
settings file only ever holds non-secret preferences.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from deckforge_core.config import SecretStore, Settings, data_dir
from deckforge_core.gui import models
from deckforge_core.gui.style import hint_label, muted_label, title_label
from deckforge_core.logging_util import get_logger

log = get_logger("deckforge.gui.settings")


class SettingsPage(QWidget):
    """Non-secret preferences in the settings file, keys in the credential store."""

    settings_saved = Signal()

    def __init__(
        self,
        settings: Optional[Settings] = None,
        secrets: Optional[SecretStore] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.settings = settings or Settings()
        self.secrets = secrets or SecretStore()

        self.title = title_label("Settings")

        self.local_only = QCheckBox("Local-only mode (no cloud calls)")
        self.local_only.setToolTip(
            "With local-only on, planning uses the deterministic rule-based planner "
            "and nothing is sent to a provider."
        )
        self.local_only.setChecked(bool(self.settings.get("local_only", True)))

        self.provider_combo = QComboBox()
        for provider in models.available_llm_providers():
            self.provider_combo.addItem(provider, provider)
        _select(self.provider_combo, str(self.settings.get("llm_provider") or ""))

        self.model_plan = QLineEdit(str(self.settings.get("llm_model_plan") or ""))
        self.model_hard = QLineEdit(str(self.settings.get("llm_model_hard") or ""))
        self.model_vision = QLineEdit(str(self.settings.get("llm_model_vision") or ""))
        self.max_iterations = QSpinBox()
        self.max_iterations.setRange(1, 3)
        self.max_iterations.setValue(int(self.settings.get("max_qa_iterations", 3)))

        self.engine_combo = QComboBox()
        for engine in ("auto", "powerpoint-com", "libreoffice", "none"):
            self.engine_combo.addItem(engine, engine)
        _select(self.engine_combo, str(self.settings.get("render_engine") or "auto"))

        backends = ", ".join(models.available_render_backends())
        self.backend_hint = muted_label(f"Slide renderers detected: {backends}")

        generation = QGroupBox("Generation")
        generation_form = QFormLayout(generation)
        generation_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        generation_form.addRow("", self.local_only)
        generation_form.addRow("LLM provider", self.provider_combo)
        generation_form.addRow("Plan model", self.model_plan)
        generation_form.addRow("Heavy model", self.model_hard)
        generation_form.addRow("Vision model", self.model_vision)
        generation_form.addRow("QA iterations", self.max_iterations)

        rendering = QGroupBox("Rendering")
        rendering_layout = QVBoxLayout(rendering)
        engine_row = QFormLayout()
        engine_row.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        engine_row.addRow("Slide engine", self.engine_combo)
        rendering_layout.addLayout(engine_row)
        rendering_layout.addWidget(self.backend_hint)

        self.key_edits: dict[str, QLineEdit] = {}
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        for row, provider in enumerate(models.secret_providers()):
            label = QLabel(provider)
            field = QLineEdit()
            field.setEchoMode(QLineEdit.EchoMode.Password)
            field.setPlaceholderText("stored in the Windows Credential Manager")
            save = QPushButton("Save")
            save.clicked.connect(lambda _c=False, name=provider: self.save_key(name))
            clear = QPushButton("Remove")
            clear.clicked.connect(lambda _c=False, name=provider: self.delete_key(name))
            grid.addWidget(label, row, 0)
            grid.addWidget(field, row, 1)
            grid.addWidget(save, row, 2)
            grid.addWidget(clear, row, 3)
            self.key_edits[provider] = field
        grid.setColumnStretch(1, 1)
        keys = QGroupBox("API keys (never written to settings.json)")
        keys_layout = QVBoxLayout(keys)
        keys_layout.addLayout(grid)

        self.save_button = QPushButton("Save settings")
        self.save_button.setObjectName("Primary")
        self.save_button.clicked.connect(self.save)
        self.reveal_button = QPushButton("Show key")
        self.reveal_button.setCheckable(True)
        self.reveal_button.toggled.connect(self._toggle_reveal)
        self.status = QLabel("")
        self.status.setObjectName("Muted")
        self.status.setWordWrap(True)

        buttons = QHBoxLayout()
        buttons.addWidget(self.save_button)
        buttons.addWidget(self.reveal_button)
        buttons.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)
        layout.addWidget(self.title)
        layout.addWidget(
            hint_label(
                f"Settings file: {models.settings_file(self.settings)}  ·  "
                f"data directory: {data_dir()}"
            )
        )
        layout.addWidget(generation)
        layout.addWidget(rendering)
        layout.addWidget(keys)
        layout.addStretch(1)
        layout.addLayout(buttons)
        layout.addWidget(self.status)

        self.load_key_status()

    # --- non-secret settings ---
    def save(self) -> None:
        try:
            self.settings.update(
                local_only=self.local_only.isChecked(),
                llm_provider=str(self.provider_combo.currentData() or "anthropic"),
                llm_model_plan=self.model_plan.text().strip(),
                llm_model_hard=self.model_hard.text().strip(),
                llm_model_vision=self.model_vision.text().strip(),
                max_qa_iterations=self.max_iterations.value(),
                render_engine=str(self.engine_combo.currentData() or "auto"),
            )
        except Exception as exc:
            self.show_error(str(exc))
            return
        log.info("settings saved to %s", models.settings_file(self.settings))
        self.status.setText("Settings saved.")
        self.settings_saved.emit()

    # --- secrets ---
    def load_key_status(self) -> None:
        for provider, field in self.key_edits.items():
            stored = bool(self.secrets.get(provider))
            field.setText("")
            field.setPlaceholderText(
                "stored — type a new key to replace" if stored else "not set"
            )

    def save_key(self, provider: str) -> None:
        field = self.key_edits.get(provider)
        if field is None:
            return
        value = field.text().strip()
        if not value:
            self.status.setText(f"No key entered for {provider}.")
            return
        try:
            self.secrets.set(provider, value)
        except Exception as exc:
            self.show_error(str(exc))
            return
        field.clear()
        self.load_key_status()
        self.status.setText(f"Key for {provider} stored in the credential manager.")

    def delete_key(self, provider: str) -> None:
        self.secrets.delete(provider)
        self.load_key_status()
        self.status.setText(f"Removed stored key for {provider}.")

    def has_key(self, provider: str) -> bool:
        return bool(self.secrets.get(provider))

    def show_error(self, message: str) -> None:
        QMessageBox.warning(self, "DeckForge", message)

    # --- internals ---
    def _toggle_reveal(self, checked: bool) -> None:
        mode = QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
        for field in self.key_edits.values():
            field.setEchoMode(mode)

    def storage_path(self) -> Path:
        return models.settings_file(self.settings)


def _select(combo: QComboBox, value: str) -> None:
    index = combo.findData(value)
    if index >= 0:
        combo.setCurrentIndex(index)
