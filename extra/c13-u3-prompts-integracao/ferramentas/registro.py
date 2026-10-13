"""Build the record of generated integration test cases: one row per test function.

For each suite: run pytest with a junit report on the ORIGINAL code, group the
collected items by test function, take the first docstring line (AST) and assign
one primary integration class by keyword rules (reviewed by hand afterwards).
Prints markdown tables plus a class-coverage matrix.
"""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = Path(os.environ.get("LST_REPO", ROOT.parents[1]))  # pacote em <repo>/extra/<pasta>
SUITES = {
    "P0": ["tests/integration"],
    "P1 v1": ["tests/test_gen_p1_v1.py"],
    "P2 v1": ["tests/test_gen_p2_v1.py"],
    "P1 v2": ["tests/test_gen_p1_v2.py"],
    "P2 v2": ["tests/test_gen_p2_v2.py"],
}
CLASSES = [
    (
        "CFGINV",
        r"invalid|invalida|fora_da_faixa|reject|rejeita|limites_da_faixa|limit_values|accept_closed|aceita_limites",
    ),
    ("MAL200", r"fora_do_formato|nao_especificad|200_invalido_falha"),
    (
        "DADOS",
        r"amostra|sampled|dados_enviados|chave_da_api_nunca|benignas|only_sampled|leaves_the_machine",
    ),
    (
        "CASC",
        r"degrad|modo_fixado|fixed_mode|fixed_structured|auto_mode|modo_auto|400_apos|unrelated_400|nao_degrada",
    ),
    (
        "4XX",
        r"4xx|401|non_transient|chave_invalida|invalid_key|chave_recusada|authentication|revoked",
    ),
    ("TRANS", r"transit|503|5xx|429|server_error|rate_limit|max_retries"),
    ("REDE", r"timeout|network|conexao|connection"),
    (
        "INV200",
        r"conteudo_invalido|invalid_200|invalid_reply|parse_retr|resposta_invalida|unexplained|nao_explicados|recover|truncated|invalido_seguido",
    ),
    ("OK200", r"tolerad|severidades_validas|formatos_tolerados|variacoes"),
    (
        "CFG",
        r"dotenv|max_tokens|modelo_configurado|base_url|response_format_enviado|structured_mode_is_applied|configuration_reaches|run_pipeline_aplica|json_schema_declara|configuracao_padrao|configuracao_pelo",
    ),
    ("REQ", r"post|requisicao|request|chat_completions|uma_chamada|envia_uma|explicacao_de_cada"),
    (
        "CLI",
        r"cli|dry_run|arquivo|missing_log|missing_api|chave_ausente|sem_chave|exit|log_sem_eventos|pipeline_propaga|run_pipeline_propaga",
    ),
]


def classify(name: str) -> str:
    for label, pattern in CLASSES:
        if re.search(pattern, name):
            return label
    return "?"


def docstrings(paths: list[Path]) -> dict[str, str]:
    found: dict[str, str] = {}
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name.startswith(
                "test_"
            ):
                doc = (ast.get_docstring(node) or "").strip().splitlines()
                found[node.name] = doc[0] if doc else ""
    return found


def run_suite(targets: list[str]) -> list[tuple[str, str]]:
    report = ROOT / "medidas" / "registro.xml"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            *targets,
            "-q",
            "--no-cov",
            "-p",
            "no:cacheprovider",
            "--tb=no",
            "-o",
            "markers=integration: x",
            f"--junitxml={report}",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
        timeout=600,
    )
    items = []
    for case in ET.parse(report).getroot().iter("testcase"):
        name = case.get("name").split("[")[0]
        if case.find("failure") is not None or case.find("error") is not None:
            status = "falhou"
        elif case.find("skipped") is not None:
            status = "xfail"
        else:
            status = "passou"
        items.append((name, status))
    report.unlink()
    return items


def main() -> None:
    matrix: dict[str, Counter[str]] = {}
    out: dict[str, list[dict[str, object]]] = {}
    for suite, targets in SUITES.items():
        paths = [
            p
            for t in targets
            for p in ((REPO / t).rglob("test_*.py") if (REPO / t).is_dir() else [REPO / t])
        ]
        docs = docstrings(paths)
        grouped: dict[str, Counter[str]] = defaultdict(Counter)
        order: list[str] = []
        for name, status in run_suite(targets):
            if name not in grouped:
                order.append(name)
            grouped[name][status] += 1
        rows = []
        for name in order:
            label = classify(name + " " + docs.get(name, "").lower().replace(" ", "_"))
            rows.append(
                {
                    "teste": name,
                    "classe": label,
                    "doc": docs.get(name, ""),
                    "res": dict(grouped[name]),
                }
            )
        out[suite] = rows
        matrix[suite] = Counter(r["classe"] for r in rows)
    (ROOT / "medidas" / "registro.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    labels = [c for c, _ in CLASSES] + ["?"]
    print("classe  " + " ".join(f"{s:>6}" for s in SUITES))
    for label in labels:
        print(f"{label:<7} " + " ".join(f"{matrix[s].get(label, 0):>6}" for s in SUITES))
    for suite, rows in out.items():
        unknown = [r["teste"] for r in rows if r["classe"] == "?"]
        if unknown:
            print(suite, "sem classe:", unknown)


if __name__ == "__main__":
    main()
