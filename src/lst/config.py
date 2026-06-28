"""Runtime configuration loaded from the environment or a ``.env`` file.

The only stage that needs configuration is the LLM Explainer; everything
upstream is deterministic and offline. Centralising the settings in a
single ``BaseSettings`` class keeps the contract explicit: the CLI builds
one :class:`Settings` instance, hands it to the Explainer, and reads
each knob from a well-documented field.

The Explainer speaks the OpenAI-compatible chat-completions protocol, so
LST is not tied to any single provider: Ollama Cloud (the default), GLM
(Z.ai), OpenRouter, or OpenAI itself all work by changing only
:attr:`Settings.llm_base_url`, :attr:`Settings.llm_model`, and
:attr:`Settings.llm_api_key` -- no code change required.

Design rules enforced here:

* Fail loud on missing credentials -- :attr:`Settings.llm_api_key` has
  no default, so ``Settings()`` raises a
  :class:`pydantic.ValidationError` at startup when neither ``LLM_API_KEY``
  nor the legacy ``OLLAMA_API_KEY`` is exported (or present in ``.env``).
  A silent ``""`` key would surface as an opaque 401 from the provider
  half-way through a run.
* Backward-compatible env names -- the three provider fields were named
  ``OLLAMA_*`` in v1.0.0 and are ``LLM_*`` now. Each one accepts both
  spellings through :class:`pydantic.AliasChoices`, so a v1.0.0 ``.env``
  keeps loading unchanged. ``case_sensitive=False`` makes the match
  case-insensitive (``LLM_API_KEY`` and ``llm_api_key`` are equivalent),
  and ``populate_by_name=True`` keeps the field names usable as direct
  keyword arguments alongside their aliases.
* Narrow numeric bounds -- ``llm_timeout_seconds`` and
  ``llm_max_retries`` have tight ``ge``/``le`` guards so a typo
  (``60000`` seconds instead of ``60``) is rejected at load time.
"""

from __future__ import annotations

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-backed configuration for the CLI.

    Fields map to environment variables (case-insensitive) and can also
    be supplied through a local ``.env`` file -- the CLI entry point
    loads the file automatically via :class:`SettingsConfigDict`. The
    three provider fields each accept their legacy ``OLLAMA_*`` name as
    an alias, so a v1.0.0 ``.env`` keeps working untouched.

    Attributes:
        llm_api_key: Bearer token for the LLM provider. Required; no
            default -- an unset key is a startup error, not a runtime
            surprise. Legacy env alias: ``OLLAMA_API_KEY``.
        llm_model: Model identifier understood by the configured provider
            (e.g. ``gpt-oss:20b`` on Ollama Cloud, ``glm-5.2`` on GLM).
            Legacy env alias: ``OLLAMA_MODEL``.
        llm_base_url: OpenAI-compatible chat-completions base URL.
            Defaults to Ollama Cloud; point it at any compatible
            provider. Legacy env alias: ``OLLAMA_BASE_URL``.
        llm_timeout_seconds: Per-request wall-clock budget handed to the
            HTTP client. Bounded to ``[1.0, 300.0]``.
        llm_max_retries: Automatic retry budget for transient failures
            (HTTP 5xx, rate-limit). Bounded to ``[0, 5]``.
        llm_max_tokens: Hard cap on tokens the LLM may emit per response.
            Bounded to ``[64, 4096]``; the default ``1024`` leaves room
            for multi-sentence pt-BR explanations without truncation.

    Example:
        >>> from lst.config import Settings
        >>> settings = Settings()  # loads from environment + .env
        >>> settings.llm_model
        'gpt-oss:20b'
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        populate_by_name=True,
        extra="ignore",
    )

    llm_api_key: str = Field(
        ...,
        min_length=1,
        validation_alias=AliasChoices("LLM_API_KEY", "OLLAMA_API_KEY"),
        description="Bearer token for the LLM provider (required).",
    )
    llm_model: str = Field(
        default="gpt-oss:20b",
        min_length=1,
        validation_alias=AliasChoices("LLM_MODEL", "OLLAMA_MODEL"),
        description="Model identifier understood by the configured LLM provider.",
    )
    llm_base_url: str = Field(
        default="https://ollama.com/v1",
        min_length=1,
        validation_alias=AliasChoices("LLM_BASE_URL", "OLLAMA_BASE_URL"),
        description="OpenAI-compatible chat-completions base URL.",
    )
    llm_timeout_seconds: float = Field(
        default=60.0,
        ge=1.0,
        le=300.0,
        description="Per-request HTTP timeout budget, in seconds.",
    )
    llm_max_retries: int = Field(
        default=2,
        ge=0,
        le=5,
        description="Automatic retry budget for transient LLM failures.",
    )
    llm_max_tokens: int = Field(
        default=1024,
        ge=64,
        le=4096,
        description=(
            "Maximum tokens the LLM may emit in a single response. Generous "
            "default ensures multi-sentence pt-BR explanations aren't truncated."
        ),
    )
