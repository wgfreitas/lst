"""Runtime configuration loaded from the environment or a ``.env`` file.

The only stage that needs configuration is the LLM Explainer; everything
upstream is deterministic and offline. Centralising the settings in a
single ``BaseSettings`` class keeps the contract explicit: the CLI builds
one :class:`Settings` instance, hands it to the Explainer, and reads
each knob from a well-documented field.

Design rules enforced here:

* Fail loud on missing credentials -- :attr:`Settings.ollama_api_key`
  has no default, so ``Settings()`` raises a
  :class:`pydantic.ValidationError` at startup if ``OLLAMA_API_KEY`` is
  not exported (or present in ``.env``). A silent ``""`` key would
  surface as an opaque 401 from Ollama Cloud half-way through a run.
* Case-insensitive env names -- both ``OLLAMA_API_KEY`` and
  ``ollama_api_key`` resolve to the same field, which is friendlier to
  shells that lowercase their environment.
* Narrow numeric bounds -- ``llm_timeout_seconds`` and
  ``llm_max_retries`` have tight ``ge``/``le`` guards so a typo
  (``60000`` seconds instead of ``60``) is rejected at load time.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-backed configuration for the CLI.

    Fields map to environment variables of the same name (case-insensitive)
    and can also be supplied through a local ``.env`` file -- the CLI
    entry point loads the file automatically via
    :class:`SettingsConfigDict`.

    Attributes:
        ollama_api_key: Bearer token for Ollama Cloud. Required; no
            default -- an unset key is a startup error, not a runtime
            surprise.
        ollama_model: Model identifier available on the caller's Ollama
            Cloud plan (e.g. ``gpt-oss:20b``, ``gpt-oss:120b``).
        ollama_base_url: OpenAI-compatible chat-completions base URL.
            Override only when pointing at a self-hosted proxy.
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
        >>> settings.ollama_model
        'gpt-oss:20b'
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    ollama_api_key: str = Field(
        ...,
        min_length=1,
        description="Bearer token for Ollama Cloud (required).",
    )
    ollama_model: str = Field(
        default="gpt-oss:20b",
        min_length=1,
        description="Model identifier available on your Ollama Cloud plan.",
    )
    ollama_base_url: str = Field(
        default="https://ollama.com/v1",
        min_length=1,
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
