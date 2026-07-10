# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.2.0] - 2026-07-09

### Added
- IPv6 support in IP extraction: full form, compressed (`::`), loopback,
  link-local, and IPv4-mapped literals are now recognised alongside IPv4.
  Zone-ID'd literals (`fe80::1%eth0`) are captured whole and deliberately
  discarded — never silently stripped to the bare address. IPv4-mapped
  literals (`::ffff:192.0.2.1`) are returned verbatim as a single IPv6
  token. A dedicated calibrated fixture
  (`tests/fixtures/auth_ipv6_sample.log`) proves IPv6 evidence flows
  end-to-end through parser -> aggregator -> detector.
- GitHub Actions CI workflow: runs ruff, mypy, and pytest on every push to
  main and pull request, pinned to Python 3.11. Status badge in the README.

## [1.1.0] - 2026-06-28

### Added
- Multi-provider support for any OpenAI-compatible endpoint (verified against
  Ollama Cloud, GLM Coding/Z.ai). The LLM client was renamed `OllamaClient` ->
  `OpenAICompatClient` to reflect this.
- `LLM_STRUCTURED_MODE` setting (auto/json_schema/json_object/none): adaptive
  structured-output strategy. 'auto' tries JSON Schema first, degrading
  gracefully for providers that reject it.
- Strict JSON Schema response format, which forces the required fields
  (explanation, severity, next_action) at the API level. Resolves the
  field-truncation seen with some providers.
- `LLM_PARSE_RETRIES` setting (default 1): re-requests when a provider returns
  an empty or unparseable 200-OK reply.
- "Eventos não explicados" report footer: events detected but not explainable
  by the LLM are listed instead of silently dropped.

### Changed
- Environment variables renamed `OLLAMA_*` -> `LLM_*` (`LLM_API_KEY`,
  `LLM_MODEL`, `LLM_BASE_URL`). The legacy `OLLAMA_*` names still work via
  aliases — existing `.env` files are not broken.
- CLI error messages no longer hardcode "Ollama Cloud".

## [1.0.0] - 2026-04-19

First stable release: the complete five-stage triage pipeline behind the
`lst` CLI. Consolidates everything shipped on top of the initial 0.1.0
scaffold and matches the `v1.0.0` git tag.

### Added
- **Parser stage** — streaming log reader (`iter_log_lines`) plus drain3
  template mining (`mine_templates`) with per-line IP and username extraction.
- **Aggregator stage** — per-template statistics: event counts, rate and
  peak-rate per minute, unique IP/user cardinalities, and sample IPs/users.
- **Detector stage** — five deterministic rules over the aggregated templates:
  brute force (source-IP cardinality), high-risk pattern, novelty, spike, and
  variety.
- **Explainer stage** — LLM enrichment over an OpenAI-compatible
  chat-completions endpoint via the official `openai` SDK, with JSON-mode and an
  automatic fallback when the model rejects `response_format`, a tolerant
  response parser, and a pt-BR explanation, severity, and next-action per
  flagged event.
- **Reporter stage** — pt-BR Markdown triage report.
- **CLI** — `lst scan` with `--dry-run` (offline, no API key required),
  `-o/--output`, and `-v/--verbose`; `lst version`.
- **Configuration** — `Settings` (pydantic-settings) loaded from the
  environment or a local `.env`, with fail-loud validation of the API key and
  bounded numeric knobs.

## [0.1.0] - 2026-04-18

### Added
- Initial project scaffold using the src-layout.
- `pyproject.toml` with Hatchling build backend, runtime deps (Typer, drain3,
  Pydantic v2, pydantic-settings, httpx, openai) and developer toolchain
  (ruff strict, mypy strict, pytest with a 70% coverage gate,
  pytest-asyncio, pytest-mock, respx).
- CLI entry point `lst` registered via `[project.scripts]`.
- Architecture diagram in `docs/architecture.md` (Mermaid, top-down).
- Editor and environment config stubs (`.editorconfig`, `.env.example`).
- Developer workflow automation in `Makefile` (`help`, `install`, `test`,
  `lint`, `format`, `typecheck`, `run`, `clean`).
- Package marker `src/lst/__init__.py` exposing `__version__`.
- PEP 561 typing marker at `src/lst/py.typed`.
- Smoke test suite asserting the package imports and version shape.

[Unreleased]: https://github.com/wgfreitas/lst/compare/v1.2.0...HEAD
[1.2.0]: https://github.com/wgfreitas/lst/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/wgfreitas/lst/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/wgfreitas/lst/compare/v0.1.0...v1.0.0
[0.1.0]: https://github.com/wgfreitas/lst/releases/tag/v0.1.0
