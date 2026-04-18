# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/your-org/lst/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/your-org/lst/releases/tag/v0.1.0
