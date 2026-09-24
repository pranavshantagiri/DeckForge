"""Application paths and settings.

All user data lives under ``%APPDATA%\\DeckForge`` on Windows
(``platformdirs.user_data_dir``). Secrets are *never* stored here in plaintext;
API keys go to the Windows Credential Manager via keyring.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import platformdirs

from deckforge_core.errors import ConfigError

APP_NAME = "DeckForge"
APP_AUTHOR = "DeckForge"


def data_dir() -> Path:
    """Root data directory, e.g. C:\\Users\\x\\AppData\\Roaming\\DeckForge."""
    return Path(platformdirs.user_data_dir(APP_NAME, APP_AUTHOR))


def ensure_dirs() -> dict[str, Path]:
    """Create and return the canonical directory layout."""
    root = data_dir()
    layout = {
        "root": root,
        "packs": root / "packs",
        "decks": root / "decks",
        "db": root / "db",
        "logs": root / "logs",
        "cache": root / "cache",
        "thumbnails": root / "cache" / "thumbnails",
        "renders": root / "cache" / "renders",
        "vectors": root / "db" / "vectors",
    }
    for path in layout.values():
        path.mkdir(parents=True, exist_ok=True)
    return layout


def logs_dir() -> Path:
    return ensure_dirs()["logs"]


class Settings:
    """Persisted non-secret settings (providers, image sources, engines).

    API keys are handled separately through keyring-backed :class:`SecretStore`.
    Settings are kept under the data directory, never next to code.
    """

    FILE_NAME = "settings.json"

    def __init__(self, root: Path | None = None) -> None:
        self._root = root or data_dir()
        self._path = self._root / self.FILE_NAME
        self._data: dict[str, Any] = self._load()

    # --- defaults ---
    DEFAULTS: dict[str, Any] = {
        "local_only": True,  # privacy: no cloud calls unless the user opts in
        "llm_provider": "anthropic",
        "llm_model_plan": "claude-sonnet-5",
        "llm_model_hard": "claude-opus-5-5",
        "llm_model_vision": "claude-opus-5-5",
        "max_qa_iterations": 3,
        "image_sources": ["unsplash", "pexels", "local"],
        "ai_image_generation_enabled": False,
        "render_engine": "auto",  # auto | powerpoint-com | libreoffice
        "corpus_sample_size": 200,
        "recent_decks": [],
        "recent_packs": [],
    }

    def _load(self) -> dict[str, Any]:
        if not self._path.exists():
            return dict(self.DEFAULTS)
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:  # pragma: no cover
            raise ConfigError(f"Corrupt settings file {self._path}") from exc
        merged = dict(self.DEFAULTS)
        merged.update(raw or {})
        return merged

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    SECRET_HINTS = ("key", "token", "secret", "password", "api")

    def set(self, key: str, value: Any) -> None:
        lowered = key.lower()
        if any(hint in lowered for hint in self.SECRET_HINTS):
            raise ConfigError(
                f"refusing to store secret-like key {key!r} in settings; "
                "use SecretStore (Windows Credential Manager)"
            )
        self._data[key] = value
        self.save()

    def update(self, **kwargs: Any) -> None:
        self._data.update(kwargs)
        self.save()

    def save(self) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._data, indent=2), encoding="utf-8")

    @property
    def local_only(self) -> bool:
        return bool(self._data.get("local_only", True))

    @property
    def as_dict(self) -> dict[str, Any]:
        return dict(self._data)


class SecretStore:
    """API keys via the OS credential manager (keyring). Never on disk."""

    SERVICE = "DeckForge"

    def get(self, provider: str, default: str | None = None) -> str | None:
        try:
            import keyring

            value = keyring.get_password(self.SERVICE, provider)
        except Exception:  # pragma: no cover - keyring backends vary
            value = None
        return value or default

    def set(self, provider: str, value: str) -> None:
        try:
            import keyring

            keyring.set_password(self.SERVICE, provider, value)
        except Exception as exc:  # pragma: no cover
            raise ConfigError(f"Could not store credential for {provider}") from exc

    def delete(self, provider: str) -> None:
        try:
            import keyring

            try:
                keyring.delete_password(self.SERVICE, provider)
            except Exception:
                pass
        except Exception:  # pragma: no cover
            pass
