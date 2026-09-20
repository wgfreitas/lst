"""Unit tests for :mod:`lst.envcheck` -- the pure parse / check / render steps.

Every test name carries the case ID from the task contract (N1-N2, L1-L7,
E1-E4). Tests that pin a variation of a case (alias precedence, findings in
the example file) reuse the nearest ID with a descriptive suffix. The file
I/O and exit-code layer is covered in :mod:`tests.test_cli`.

Values in every ``.env`` text below are ``fake-`` placeholders; the E4 test
uses the sentinel from the task to prove no value ever reaches the output.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import AliasChoices

from lst.config import Settings
from lst.envcheck import (
    CheckedFile,
    EnvFinding,
    FindingKind,
    FindingSeverity,
    check_env,
    parse_dotenv,
    render_report,
)

_EXAMPLE_PATH = Path(__file__).resolve().parent.parent / ".env.example"

_CONTRACT_KEYS = (
    "LLM_API_KEY",
    "LLM_MODEL",
    "LLM_BASE_URL",
    "LLM_TIMEOUT_SECONDS",
    "LLM_MAX_RETRIES",
    "LLM_MAX_TOKENS",
    "LLM_STRUCTURED_MODE",
    "LLM_PARSE_RETRIES",
)

_FULL_ENV = "\n".join(f"{key}=fake-{key.lower()}" for key in _CONTRACT_KEYS) + "\n"

_LEGACY_ENV = "OLLAMA_API_KEY=fake-key\nOLLAMA_MODEL=fake-model\nOLLAMA_BASE_URL=http://fake\n"

_SENTINEL = "VALOR-QUE-NAO-PODE-VAZAR"


@pytest.fixture
def example_text() -> str:
    """Return the real, versioned ``.env.example`` -- the contract under test."""
    return _EXAMPLE_PATH.read_text(encoding="utf-8")


def _kinds(findings: tuple[EnvFinding, ...]) -> list[FindingKind]:
    """Return the kinds of ``findings`` in report order."""
    return [finding.kind for finding in findings]


# --- Normal -----------------------------------------------------------------


def test_n1_full_llm_env_matches_contract_without_findings(example_text: str) -> None:
    """All 8 LLM_* keys filled -> no findings, 8 keys checked, OK summary."""
    report = check_env(example_text, _FULL_ENV)

    assert report.findings == ()
    assert report.checked_key_count == 8
    assert report.ok is True
    assert render_report(report) == "OK: 8 chaves conferidas, sem problemas"


def test_n1_parse_dotenv_skips_blank_and_comment_lines(example_text: str) -> None:
    """The real example parses to exactly the 8 contract keys, in file order."""
    parsed = parse_dotenv(example_text)

    assert tuple(entry.key for entry in parsed.entries) == _CONTRACT_KEYS
    assert parsed.malformed_lines == ()

    api_key_entry = parsed.find("LLM_API_KEY")
    model_entry = parsed.find("LLM_MODEL")
    assert api_key_entry is not None and api_key_entry.is_empty is True
    assert model_entry is not None and model_entry.value == "gpt-oss:20b"


def test_n2_legacy_aliases_satisfy_canonical_keys_with_warnings(example_text: str) -> None:
    """A v1.0.0 .env (OLLAMA_* only) yields 3 legacy warnings and zero errors."""
    report = check_env(example_text, _LEGACY_ENV)

    assert _kinds(report.findings) == [FindingKind.LEGACY] * 3
    assert all(finding.severity is FindingSeverity.WARNING for finding in report.findings)
    assert report.error_count == 0
    assert report.ok is True

    rendered = render_report(report)
    assert "[AVISO] OLLAMA_API_KEY: nome legado — prefira LLM_API_KEY" in rendered
    assert "[AVISO] OLLAMA_MODEL: nome legado — prefira LLM_MODEL" in rendered
    assert "[AVISO] OLLAMA_BASE_URL: nome legado — prefira LLM_BASE_URL" in rendered
    assert rendered.endswith("0 erro(s), 3 aviso(s)")


def test_n2_legacy_alias_table_mirrors_settings_aliases(example_text: str) -> None:
    """Every AliasChoices pair in Settings is recognised as legacy -> canonical."""
    alias_pairs = [
        field.validation_alias.choices
        for field in Settings.model_fields.values()
        if isinstance(field.validation_alias, AliasChoices)
    ]
    assert len(alias_pairs) == 3

    for canonical, legacy in alias_pairs:
        report = check_env(example_text, f"LLM_API_KEY=fake-key\n{legacy}=fake-value\n")

        assert _kinds(report.findings) == [FindingKind.LEGACY], legacy
        assert f"prefira {canonical}" in render_report(report)


def test_n2_alias_with_empty_value_is_missing_and_legacy(example_text: str) -> None:
    """An empty legacy alias does not satisfy the required key: missing + legacy."""
    report = check_env(example_text, "OLLAMA_API_KEY=\n")

    assert _kinds(report.findings) == [FindingKind.MISSING, FindingKind.LEGACY]
    assert report.ok is False


def test_n2_canonical_key_takes_precedence_over_legacy_alias(example_text: str) -> None:
    """Like Settings' AliasChoices, an empty LLM_API_KEY wins over a filled OLLAMA_API_KEY."""
    report = check_env(example_text, "LLM_API_KEY=\nOLLAMA_API_KEY=fake-key\n")

    assert _kinds(report.findings) == [FindingKind.MISSING, FindingKind.LEGACY]
    assert report.ok is False


# --- Limits -----------------------------------------------------------------


def test_l1_required_key_with_empty_value_is_missing_error(example_text: str) -> None:
    """``LLM_API_KEY=`` counts as missing (error) and cites its line."""
    report = check_env(example_text, "LLM_API_KEY=\n")

    assert len(report.findings) == 1
    finding = report.findings[0]
    assert finding.kind is FindingKind.MISSING
    assert finding.severity is FindingSeverity.ERROR
    assert finding.key == "LLM_API_KEY"
    assert finding.lines == (1,)
    assert report.ok is False

    rendered = render_report(report)
    assert "[ERRO] LLM_API_KEY: obrigatória e vazia (linha 1)" in rendered
    assert rendered.endswith("1 erro(s), 0 aviso(s)")


def test_l2_unknown_key_is_warning_with_line(example_text: str) -> None:
    """A dead variable such as LST_HTTP_TIMEOUT is an unknown-key warning, exit stays OK."""
    report = check_env(example_text, _FULL_ENV + "LST_HTTP_TIMEOUT=30\n")

    assert len(report.findings) == 1
    finding = report.findings[0]
    assert finding.kind is FindingKind.UNKNOWN
    assert finding.severity is FindingSeverity.WARNING
    assert finding.key == "LST_HTTP_TIMEOUT"
    assert finding.lines == (9,)
    assert report.ok is True
    assert "[AVISO] LST_HTTP_TIMEOUT: chave desconhecida (linha 9)" in render_report(report)


def test_l3_export_prefix_and_enclosing_quotes_are_accepted(example_text: str) -> None:
    """``export KEY="value"`` parses to the bare key and unquoted value; no findings."""
    parsed = parse_dotenv("export LLM_MODEL=\"fake-model\"\nexport LLM_BASE_URL='http://fake'\n")

    assert [(entry.key, entry.value) for entry in parsed.entries] == [
        ("LLM_MODEL", "fake-model"),
        ("LLM_BASE_URL", "http://fake"),
    ]
    assert parsed.malformed_lines == ()

    report = check_env(example_text, 'LLM_API_KEY=fake-key\nexport LLM_MODEL="fake-model"\n')
    assert report.findings == ()


def test_l4_optional_key_with_empty_value_is_empty_error(example_text: str) -> None:
    """``LLM_MODEL=`` is an error: Settings rejects the empty string instead of defaulting."""
    report = check_env(example_text, "LLM_API_KEY=fake-key\nLLM_MODEL=\n")

    assert len(report.findings) == 1
    finding = report.findings[0]
    assert finding.kind is FindingKind.EMPTY
    assert finding.severity is FindingSeverity.ERROR
    assert finding.key == "LLM_MODEL"
    assert finding.lines == (2,)
    assert report.ok is False
    assert "[ERRO] LLM_MODEL: vazia" in render_report(report)
    assert "(linha 2)" in render_report(report)


def test_l5_duplicate_key_warns_with_both_lines_and_last_wins(example_text: str) -> None:
    """A key on two lines is one duplicate warning citing both; the last value is effective."""
    env_text = "LLM_API_KEY=fake-first\n\nLLM_API_KEY=fake-last\n"
    parsed = parse_dotenv(env_text)

    assert len(parsed.entries) == 1
    assert parsed.entries[0].value == "fake-last"
    assert parsed.entries[0].lines == (1, 3)

    report = check_env(example_text, env_text)
    assert len(report.findings) == 1
    finding = report.findings[0]
    assert finding.kind is FindingKind.DUPLICATE
    assert finding.severity is FindingSeverity.WARNING
    assert finding.key == "LLM_API_KEY"
    assert finding.lines == (1, 3)
    assert report.ok is True
    assert "[AVISO] LLM_API_KEY: chave repetida (linhas 1 e 3) — a última vale" in render_report(
        report
    )


def test_l5_duplicate_key_in_example_file_is_reported_with_file_label(
    example_text: str,
) -> None:
    """A repeated key in the contract file itself is a warning naming that file."""
    first_appended_line = example_text.count("\n") + 1
    contract_with_duplicate = example_text + "LLM_MODEL=\nLLM_MODEL=fake-model\n"
    report = check_env(contract_with_duplicate, "LLM_API_KEY=fake-key\n")

    assert _kinds(report.findings) == [FindingKind.DUPLICATE]
    finding = report.findings[0]
    assert finding.file is CheckedFile.EXAMPLE
    assert finding.key == "LLM_MODEL"
    assert finding.lines == (14, first_appended_line, first_appended_line + 1)
    assert report.checked_key_count == 8
    assert (
        f"chave repetida no arquivo de exemplo (linhas 14, {first_appended_line} e "
        f"{first_appended_line + 1})"
    ) in render_report(report)


def test_l6_empty_env_yields_exactly_one_missing_for_the_api_key(example_text: str) -> None:
    """A 0-byte .env has one finding only: LLM_API_KEY is the sole required key."""
    report = check_env(example_text, "")

    assert len(report.findings) == 1
    finding = report.findings[0]
    assert finding.kind is FindingKind.MISSING
    assert finding.key == "LLM_API_KEY"
    assert finding.lines == ()
    assert report.ok is False

    rendered = render_report(report)
    assert "[ERRO] LLM_API_KEY: obrigatória e ausente" in rendered
    assert rendered.endswith("1 erro(s), 0 aviso(s)")


def test_l7_key_lookup_is_case_insensitive(example_text: str) -> None:
    """``llm_api_key=...`` satisfies LLM_API_KEY, mirroring case_sensitive=False in Settings."""
    report = check_env(example_text, "llm_api_key=fake-key\n")

    assert report.findings == ()
    assert report.ok is True


# --- Errors -----------------------------------------------------------------


def test_e3_line_without_key_is_malformed_by_number_only(example_text: str) -> None:
    """A keyless line is a warning that cites the line number and never its content."""
    env_text = "LLM_API_KEY=fake-key\nfake-secret-without-key\n"
    parsed = parse_dotenv(env_text)

    assert parsed.malformed_lines == (2,)
    assert [entry.key for entry in parsed.entries] == ["LLM_API_KEY"]

    report = check_env(example_text, env_text)
    assert len(report.findings) == 1
    finding = report.findings[0]
    assert finding.kind is FindingKind.MALFORMED
    assert finding.severity is FindingSeverity.WARNING
    assert finding.key is None
    assert finding.lines == (2,)
    assert report.ok is True

    rendered = render_report(report)
    assert "[AVISO] linha 2: malformada (ignorada)" in rendered
    assert "fake-secret-without-key" not in rendered
    assert "fake-secret-without-key" not in repr(report)


def test_e3_malformed_line_in_example_file_is_reported_with_file_label(
    example_text: str,
) -> None:
    """A broken line in the contract file is a warning naming that file, not silence."""
    appended_line = example_text.count("\n") + 1
    report = check_env(example_text + "fake-secret-without-key\n", "LLM_API_KEY=fake-key\n")

    assert _kinds(report.findings) == [FindingKind.MALFORMED]
    finding = report.findings[0]
    assert finding.file is CheckedFile.EXAMPLE
    assert finding.lines == (appended_line,)

    rendered = render_report(report)
    assert f"[AVISO] linha {appended_line} do arquivo de exemplo: malformada (ignorada)" in rendered
    assert "fake-secret-without-key" not in rendered


def test_e4_report_and_rendering_never_contain_values(example_text: str) -> None:
    """With the sentinel in every key, alias, duplicate and keyless line, it never surfaces."""
    env_lines = [f"{key}={_SENTINEL}" for key in _CONTRACT_KEYS]
    env_lines += [f"{alias}={_SENTINEL}" for alias in ("OLLAMA_API_KEY", "OLLAMA_MODEL")]
    env_lines += [f"LLM_API_KEY='{_SENTINEL}'", f"LST_HTTP_TIMEOUT={_SENTINEL}", _SENTINEL]
    report = check_env(example_text, "\n".join(env_lines) + "\n")

    assert _kinds(report.findings) == [
        FindingKind.LEGACY,
        FindingKind.LEGACY,
        FindingKind.UNKNOWN,
        FindingKind.DUPLICATE,
        FindingKind.MALFORMED,
    ]
    assert _SENTINEL not in render_report(report)
    assert _SENTINEL not in repr(report)
