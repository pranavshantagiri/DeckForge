"""`settings`: view and change persisted non-secret settings.

API keys never pass through here — the secret-refusing guard lives in
``Settings.set`` and the CLI points users at ``deckforge settings provider``.
"""

from __future__ import annotations

from typing import Any

from deckforge_core.config import Settings


def cmd_list() -> dict[str, Any]:
    return dict(Settings().as_dict)


def cmd_get(key: str) -> Any:
    return Settings().get(key)


def cmd_set(key: str, value: str) -> Any:
    parsed = _parse_value(value)
    settings = Settings()
    settings.set(key, parsed)
    return settings.get(key)


def cmd_unset(key: str) -> None:
    settings = Settings()
    if key in settings.as_dict:
        settings.set(key, settings.DEFAULTS.get(key))
    # no-op removal path is intentionally forgiving


def _parse_value(value: str) -> Any:
    lowered = value.strip().lower()
    if lowered in ("true", "false"):
        return lowered == "true"
    if lowered in ("null", "none"):
        return None
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    if "," in value:
        return [piece.strip() for piece in value.split(",")]
    return value
