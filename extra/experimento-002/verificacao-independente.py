"""Independent execution of the task-002 contract examples through the real CLI.

Run from the repository root with the project's virtualenv active::

    python extra/experimento-002/verificacao-independente.py

Each case writes fake files into a temporary directory and runs ``lst env-check``
there. Every value is a ``fake-`` placeholder or the leak sentinel; nothing real.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

LST = shutil.which("lst") or ".venv/bin/lst"
EXAMPLE = Path(".env.example").read_text(encoding="utf-8")
SENTINEL = "VALOR-QUE-NAO-PODE-VAZAR"

CONTRACT_KEYS = (
    "LLM_API_KEY",
    "LLM_MODEL",
    "LLM_BASE_URL",
    "LLM_TIMEOUT_SECONDS",
    "LLM_MAX_RETRIES",
    "LLM_MAX_TOKENS",
    "LLM_STRUCTURED_MODE",
    "LLM_PARSE_RETRIES",
)
FULL_ENV = "".join(f"{key}=fake-{key.lower()}\n" for key in CONTRACT_KEYS)
SENTINEL_ENV = (
    "".join(f"{key}={SENTINEL}\n" for key in (*CONTRACT_KEYS, "OLLAMA_API_KEY", "LST_HTTP_TIMEOUT"))
    + f"{SENTINEL}\nLLM_API_KEY={SENTINEL}\n"
)


@dataclass(frozen=True)
class Case:
    """One contract example: the ``.env`` text, the expected exit code and output fragments."""

    case_id: str
    env: str | None
    exit_code: int
    expect_stdout: tuple[str, ...] = ()
    expect_stderr: tuple[str, ...] = ()
    forbid_output: tuple[str, ...] = ()
    example: str | None = EXAMPLE


CASES = [
    Case("N1", FULL_ENV, 0, ("OK: 8 chaves conferidas, sem problemas",)),
    Case(
        "N2",
        "OLLAMA_API_KEY=fake-key\nOLLAMA_MODEL=fake-model\nOLLAMA_BASE_URL=http://fake\n",
        0,
        ("nome legado — prefira LLM_API_KEY", "0 erro(s), 3 aviso(s)"),
    ),
    Case("L1", "LLM_API_KEY=\n", 1, ("[ERRO] LLM_API_KEY", "1 erro(s), 0 aviso(s)")),
    Case("L2", FULL_ENV + "LST_HTTP_TIMEOUT=30\n", 0, ("chave desconhecida (linha 9)",)),
    Case("L3", 'LLM_API_KEY=fake-key\nexport LLM_MODEL="fake-model"\n', 0, ("sem problemas",)),
    Case("L4", "LLM_API_KEY=fake-key\nLLM_MODEL=\n", 1, ("[ERRO] LLM_MODEL", "1 erro(s)")),
    Case("L5", "LLM_API_KEY=fake-1\n# c\nLLM_API_KEY=fake-2\n", 0, ("linhas 1 e 3",)),
    Case("L6", "", 1, ("obrigatória e ausente", "1 erro(s), 0 aviso(s)")),
    Case("L7", "llm_api_key=fake-key\n", 0, ("sem problemas",)),
    Case("L8", "LLM_API_KEY = fake-key\n", 0, ("sem problemas",)),
    Case("L9", "﻿LLM_API_KEY=fake-key\n", 0, ("sem problemas",)),
    Case("L10", 'LLM_API_KEY=fake-key\nLLM_MODEL="fake-model" # c\n', 0, ("sem problemas",)),
    Case("E1", None, 2, expect_stderr=("Erro: arquivo não encontrado: .env",)),
    Case("E2", FULL_ENV, 2, expect_stderr=("não encontrado: .env.example",), example=None),
    Case(
        "E3",
        "LLM_API_KEY=fake-key\nfake-secret-without-key\n",
        0,
        ("linha 2: malformada",),
        forbid_output=("fake-secret-without-key",),
    ),
    Case("E4", SENTINEL_ENV, 0, forbid_output=(SENTINEL,)),
    Case(
        "E5",
        'LLM_API_KEY="fake-key\n',
        1,
        ("obrigatória e ausente", "linha 1: malformada"),
        forbid_output=("fake-key",),
    ),
    Case("E6", 'LLM_API_KEY="" # preencha\n', 1, ("obrigatória e vazia (linha 1)",)),
]


def run_case(case: Case) -> list[str]:
    """Run one case through the CLI and return the list of failed expectations."""
    with tempfile.TemporaryDirectory() as tmp:
        cwd = Path(tmp)
        if case.env is not None:
            (cwd / ".env").write_text(case.env, encoding="utf-8")
        if case.example is not None:
            (cwd / ".env.example").write_text(case.example, encoding="utf-8")
        done = subprocess.run(
            [LST, "env-check"], cwd=cwd, capture_output=True, text=True, check=False
        )
    output = done.stdout + done.stderr
    failures = []
    if done.returncode != case.exit_code:
        failures.append(f"exit {done.returncode}, esperado {case.exit_code}")
    failures += [f"stdout sem {s!r}" for s in case.expect_stdout if s not in done.stdout]
    failures += [f"stderr sem {s!r}" for s in case.expect_stderr if s not in done.stderr]
    failures += [f"saída contém {s!r}" for s in case.forbid_output if s in output]
    return failures


def main() -> int:
    """Run every case and print PASS/FAIL per case; exit 1 if any failed."""
    all_ok = True
    for case in CASES:
        failures = run_case(case)
        all_ok &= not failures
        print(f"{'PASS' if not failures else 'FAIL'} {case.case_id}", *failures, sep="  ")
    print("ALL PASS" if all_ok else "SOME FAILED")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
