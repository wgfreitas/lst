# LST (Log Sec Triage)

> Security log triage CLI that reduces gigabytes of raw logs to dozens of actionable events.

LST is a Python 3.11 command-line tool that applies a 4-stage pipeline — template mining, statistical aggregation, rule-based detection, and LLM-powered explanation — to turn massive security log files into structured, prioritized triage reports.

## Status

🚧 **Early development (v0.1.0)** — scaffolding and architecture defined. Core pipeline implementation in progress.

## Architecture

See [`docs/architecture.md`](docs/architecture.md) for the full pipeline diagram.

Pipeline summary:

1. **Raw logs (GB)**
2. **Parser + Template Miner (Drain3)**
3. **Aggregator** (statistics per template)
4. **Rule-based Detector** (novelty, spike, brute-force)
5. **LLM Explainer** (Ollama Cloud)
6. **Reporter** (Markdown)

The LLM is used **only for the explanation layer** — detection remains deterministic and auditable.

## Tech stack

- **Language:** Python 3.11
- **CLI:** Typer
- **Template mining:** Drain3
- **Data modeling:** Pydantic v2
- **Configuration:** pydantic-settings (`.env`)
- **LLM client:** `openai` library targeting Ollama Cloud (OpenAI-compatible endpoint)
- **Tests:** pytest + respx + coverage
- **Tooling:** ruff, mypy, hatchling

## Installation (development)

```bash
git clone https://github.com/wgfreitas/lst.git
cd lst
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Usage

> Coming soon — CLI interface in development. See [`docs/usage.md`](docs/usage.md) (to be populated in Phase 3+).

## Development

Detailed sections (prerequisites, test execution, contribution workflow, AI assistance story) will be filled in during Phase 10 of the development lab, following the *Laboratório Introdutório* reference.

## License

[MIT](LICENSE) — see the license file for terms.

## Context

This project is developed as part of the **Laboratório Introdutório: Construindo um Miniprojeto com Inteligência Artificial Generativa** (AKCIT/UFG, 2026), exploring the use of generative AI tools throughout the software development lifecycle.
