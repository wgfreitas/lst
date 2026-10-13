"""Hand-made mutation analysis of generated integration suites.

Each mutant is one textual substitution in the real LST source, chosen to model
an integration fault (a value not passed between components, a status class
handled wrongly, a guard removed). A mutant is KILLED by a suite when some test
that passes on the original code fails on the mutant (tests already failing on
the original code are ignored, since they fail for a pre-existing defect).

Usage: python mutacao.py <repo> <test_file> [<test_file> ...]
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

MUTANTS: list[tuple[str, str, str, str]] = [
    (
        "M01",
        "src/lst/explainer/client.py",
        "    return any(marker in message for marker in _RESPONSE_FORMAT_MARKERS)",
        "    return False",
        "cascata nunca degrada (todo 400 vira erro)",
    ),
    (
        "M02",
        "src/lst/explainer/client.py",
        "    return any(marker in message for marker in _RESPONSE_FORMAT_MARKERS)",
        "    return True",
        "cascata degrada em qualquer 400",
    ),
    (
        "M03",
        "src/lst/explainer/client.py",
        '"auto": ("json_schema", "json_object", "none"),',
        '"auto": ("json_schema", "none"),',
        "modo auto pula json_object",
    ),
    (
        "M04",
        "src/lst/explainer/client.py",
        "                max_tokens=self._max_tokens,\n"
        "                response_format=_RESPONSE_JSON_SCHEMA,",
        "                response_format=_RESPONSE_JSON_SCHEMA,",
        "max_tokens não enviado no modo json_schema",
    ),
    (
        "M05",
        "src/lst/explainer/client.py",
        "            max_retries=settings.llm_max_retries,",
        "            max_retries=0,",
        "LLM_MAX_RETRIES ignorado (sem novas tentativas)",
    ),
    (
        "M06",
        "src/lst/explainer/client.py",
        "            base_url=settings.llm_base_url,",
        '            base_url="https://ollama.com/v1",',
        "LLM_BASE_URL ignorado",
    ),
    (
        "M07",
        "src/lst/explainer/client.py",
        "            api_key=settings.llm_api_key,",
        '            api_key="placeholder",',
        "chave configurada não vai no Authorization",
    ),
    (
        "M08",
        "src/lst/explainer/engine.py",
        "    attempts = parse_retries + 1",
        "    attempts = 1",
        "LLM_PARSE_RETRIES ignorado no motor",
    ),
    (
        "M09",
        "src/lst/explainer/engine.py",
        "            discarded.append(event)",
        "            pass",
        "evento inválido descartado em silêncio",
    ),
    (
        "M10",
        "src/lst/explainer/engine.py",
        '    severity = Severity(parsed["severity"])',
        "    severity = Severity.MEDIUM",
        "severidade fora da lista aceita (vira medium)",
    ),
    (
        "M11",
        "src/lst/pipeline.py",
        "            parse_retries=settings.llm_parse_retries,\n",
        "",
        "pipeline não repassa LLM_PARSE_RETRIES",
    ),
    (
        "M12",
        "src/lst/pipeline.py",
        "            model=settings.llm_model,",
        '            model="gpt-oss:20b",',
        "pipeline não repassa LLM_MODEL",
    ),
    (
        "M13",
        "src/lst/explainer/parser.py",
        '        "severity": str(decoded["severity"]).strip().lower(),',
        '        "severity": str(decoded["severity"]).strip(),',
        "severidade não normalizada para minúsculas",
    ),
    (
        "M14",
        "src/lst/explainer/prompt.py",
        "_SAMPLE_PREFIX_LIMIT = 3",
        "_SAMPLE_PREFIX_LIMIT = 5",
        "mais de 3 amostras saem da máquina",
    ),
    (
        "M15",
        "src/lst/cli.py",
        "    except AuthenticationError as exc:\n"
        '        typer.echo(f"Erro de autenticação no provedor LLM: {exc}", err=True)\n'
        "        raise typer.Exit(code=1) from exc\n",
        "",
        "CLI perde a mensagem de autenticação",
    ),
    (
        "M16",
        "src/lst/cli.py",
        '        typer.echo(f"Timeout ao consultar o LLM: {exc}", err=True)\n'
        "        raise typer.Exit(code=1) from exc",
        '        typer.echo(f"Timeout ao consultar o LLM: {exc}", err=True)\n'
        "        raise typer.Exit(code=2) from exc",
        "timeout sai com código 2",
    ),
    (
        "M17",
        "src/lst/reporter/markdown.py",
        "    if discarded_events:\n"
        "        sections.append(_render_discarded_block(discarded_events))",
        "    if False:\n        sections.append(_render_discarded_block(discarded_events))",
        "relatório omite 'Eventos não explicados'",
    ),
    (
        "M18",
        "src/lst/cli.py",
        '        if dry_run:\n            return Settings(llm_api_key="dry-run-placeholder")',
        '        if False:\n            return Settings(llm_api_key="dry-run-placeholder")',
        "--dry-run passa a exigir a chave",
    ),
]


def failing_tests(repo: Path, test_files: list[str]) -> set[str]:
    report = repo / ".mut-report.json"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            *test_files,
            "-q",
            "--no-cov",
            "-p",
            "no:cacheprovider",
            "--tb=no",
            f"--junitxml={report}",
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
        timeout=900,
    )
    import xml.etree.ElementTree as ET

    failed = set()
    total = 0
    for case in ET.parse(report).getroot().iter("testcase"):
        total += 1
        if case.find("failure") is not None or case.find("error") is not None:
            failed.add(f"{case.get('classname')}::{case.get('name')}")
    report.unlink()
    if total == 0:
        failed.add("<<nenhum teste coletado>>")
    return failed


def main() -> None:
    repo = Path(sys.argv[1]).resolve()
    tests = sys.argv[2:]
    baseline = failing_tests(repo, tests)
    rows = []
    for mid, rel, old, new, desc in MUTANTS:
        path = repo / rel
        original = path.read_text(encoding="utf-8")
        assert original.count(old) == 1, f"{mid}: trecho não encontrado exatamente uma vez"
        path.write_text(original.replace(old, new), encoding="utf-8")
        try:
            failed = failing_tests(repo, tests)
        finally:
            path.write_text(original, encoding="utf-8")
        new_failures = sorted(failed - baseline)
        rows.append(
            {
                "id": mid,
                "desc": desc,
                "killed": bool(new_failures),
                "by": len(new_failures),
                "tests": new_failures,
            }
        )
    killed = sum(r["killed"] for r in rows)
    print(
        json.dumps(
            {
                "suite": tests,
                "baseline_failures": len(baseline),
                "baseline": sorted(baseline),
                "killed": killed,
                "total": len(rows),
                "rows": rows,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
