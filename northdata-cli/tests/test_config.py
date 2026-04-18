from __future__ import annotations

import pytest

from northdata_cli.config import ConfigError, resolve_api_key


def test_resolve_api_key_flag_wins(monkeypatch):
    monkeypatch.setenv("NORTHDATA_API_KEY", "env-key")
    assert resolve_api_key("flag-key") == "flag-key"


def test_resolve_api_key_from_env(monkeypatch):
    monkeypatch.setenv("NORTHDATA_API_KEY", "env-key")
    assert resolve_api_key(None) == "env-key"


def test_resolve_api_key_missing_raises(monkeypatch):
    monkeypatch.delenv("NORTHDATA_API_KEY", raising=False)
    with pytest.raises(ConfigError):
        resolve_api_key(None)


def test_resolve_api_key_empty_string_raises(monkeypatch):
    monkeypatch.setenv("NORTHDATA_API_KEY", "   ")
    with pytest.raises(ConfigError):
        resolve_api_key(None)


