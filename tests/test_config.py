"""Config tests: dirs, settings persistence, secret store separation."""

from __future__ import annotations

import json

from deckforge_core.config import Settings, data_dir


def test_settings_defaults(tmp_workspace):
    s = Settings(tmp_workspace)
    assert s.local_only is True  # privacy-first default
    assert s.get("render_engine") == "auto"
    assert s.get("ai_image_generation_enabled") is False


def test_data_dir_env_override(tmp_workspace, monkeypatch):
    monkeypatch.setenv("DECKFORGE_DATA_DIR", str(tmp_workspace))
    assert data_dir() == tmp_workspace
    Settings().set("local_only", False)
    assert Settings().get("local_only") is False


def test_settings_roundtrip(tmp_workspace):
    s = Settings(tmp_workspace)
    s.set("image_sources", ["local"])
    s2 = Settings(tmp_workspace)
    assert s2.get("image_sources") == ["local"]


def test_settings_refuse_secret_keys(tmp_workspace):
    import pytest

    from deckforge_core.errors import ConfigError

    s = Settings(tmp_workspace)
    with pytest.raises(ConfigError):
        s.set("anthropic_api_key", "sk-xxxx")
    raw = json.loads((tmp_workspace / "settings.json").read_text(encoding="utf-8"))
    # SecretStore is the only home for keys; settings must never hold them.
    assert "sk-xxxx" not in json.dumps(raw)
