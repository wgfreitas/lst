"""Summarise each generated suite: results, defects revealed, mutants killed, minimal subset.

Defects are identified from the tests that fail on the ORIGINAL code (baseline), by root cause:
  D1  LLM_TIMEOUT_SECONDS accepted but never applied (always 60 s)
  D2  200 response outside the chat.completion shape aborts the whole triage with a raw message
  D3  invalid configuration reported as "LLM_API_KEY não configurada" (misleading)
  Q   team requirement: error message does not name the cause (timeout, connection)
The minimal subset is a greedy set cover over the killed mutants plus the revealed defects.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

RULES = [
    (
        "D1",
        re.compile(
            r"timeout_configurado_vale|timeout_nos_limites|timeout_seconds_is_applied|acima_do_timeout_minimo|maximo-300s"
        ),
    ),
    (
        "D2",
        re.compile(
            r"choices-vazio|objeto-vazio|erro-dentro-de-200|corpo-vazio|\bhtml\b|corpo-html"
        ),
    ),
    ("D3", re.compile(r"configuracao_invalida|invalid_setting_is_rejected")),
    ("Q", re.compile(r"test_timeout$|test_timeout\b|network_failure")),
]


def defect_of(test_id: str) -> str:
    name = test_id.split("::", 1)[1]
    for label, pattern in RULES:
        if pattern.search(name):
            return label
    return "?"


def greedy_cover(universe: dict[str, set[str]]) -> list[str]:
    """Map target -> tests that hit it; return a small list of tests hitting every target."""
    remaining = {t for t, tests in universe.items() if tests}
    chosen: list[str] = []
    while remaining:
        counts: dict[str, int] = {}
        for target in remaining:
            for test in universe[target]:
                counts[test] = counts.get(test, 0) + 1
        best = max(counts, key=lambda t: (counts[t], t))
        chosen.append(best)
        remaining = {t for t in remaining if best not in universe[t]}
    return chosen


def main() -> None:
    for label in sys.argv[1:]:
        data = json.loads(Path(f"medidas/mut_{label}.json").read_text(encoding="utf-8"))
        baseline = data["baseline"]
        by_defect: dict[str, set[str]] = {}
        for test in baseline:
            by_defect.setdefault(defect_of(test), set()).add(test)
        universe = {f"M:{r['id']}": set(r["tests"]) for r in data["rows"] if r["killed"]}
        universe.update({f"D:{d}": tests for d, tests in by_defect.items()})
        cover = greedy_cover(universe)
        defects = ", ".join(f"{d}x{len(t)}" for d, t in sorted(by_defect.items()))
        survivors = [r["id"] for r in data["rows"] if not r["killed"]]
        print(
            f"{label:<7} falhas-base={len(baseline):<3} defeitos[{defects}] "
            f"mutantes={data['killed']}/{data['total']} vivos={survivors} "
            f"subconjunto-mínimo={len(cover)}"
        )


if __name__ == "__main__":
    main()
