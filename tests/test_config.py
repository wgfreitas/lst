"""Configuration tests: field validation and OLLAMA_* -> LLM_* retrocompat.

The v1.1.0 rename moved the three provider settings from ``OLLAMA_*`` to
``LLM_*`` while keeping the old names working through
:class:`pydantic.AliasChoices`. These tests pin that contract: a v1.0.0
``.env`` must keep loading, the new canonical names must win, and -- when
both are present -- the canonical ``LLM_*`` value takes precedence.
"""

from __future__ import annotations

import pytest

from lst.config import Settings

_PROVIDER_ENV = (
    "LLM_API_KEY",
    "LLM_MODEL",
    "LLM_BASE_URL",
    "OLLAMA_API_KEY",
    "OLLAMA_MODEL",
    "OLLAMA_BASE_URL",
)


def _clear_provider_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Drop every provider env var so a developer's shell can't leak in."""
    for name in _PROVIDER_ENV:
        monkeypatch.delenv(name, raising=False)


def test_settings_accepts_legacy_ollama_env_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A v1.0.0 .env using OLLAMA_* names still loads (retrocompat)."""
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("OLLAMA_API_KEY", "sk-legacy-1234")
    monkeypatch.setenv("OLLAMA_MODEL", "legacy-model")
    monkeypatch.setenv("OLLAMA_BASE_URL", "https://legacy.example/v1")

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.llm_api_key == "sk-legacy-1234"
    assert settings.llm_model == "legacy-model"
    assert settings.llm_base_url == "https://legacy.example/v1"


def test_settings_accepts_new_llm_env_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The new LLM_* names load as the canonical source."""
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("LLM_API_KEY", "sk-new-5678")

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.llm_api_key == "sk-new-5678"


def test_settings_prefers_llm_over_legacy_when_both_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With both names exported, the canonical LLM_* value wins."""
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("OLLAMA_API_KEY", "sk-legacy")
    monkeypatch.setenv("LLM_API_KEY", "sk-canonical")

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.llm_api_key == "sk-canonical"
