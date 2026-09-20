"""Check a local ``.env`` against the ``.env.example`` contract without exposing values.

``lst env-check`` exists because of two recurring incidents: dead variables
in ``.env`` (``LST_HTTP_TIMEOUT``, ``LST_MAX_FLAGGED_EVENTS``) that
:class:`~lst.config.Settings` silently ignored, and API keys leaked by
printing ``.env`` in a terminal. This module answers "is my ``.env``
coherent with the contract?" using key names and line numbers only.

Three pure steps, one function each:

* :func:`parse_dotenv` -- dotenv text -> :class:`ParsedDotenv`. The same
  parser reads both files and never raises, whatever the input.
* :func:`check_env` -- contract x env -> :class:`EnvReport` holding
  :class:`EnvFinding` items.
* :func:`render_report` -- report -> pt-BR text for the analyst.

Paths, file reading and exit codes belong to :mod:`lst.cli`.

Design rules enforced here:

* Values never leave the parser. Findings, the report and the rendered
  text carry keys and line numbers only, so the output can be pasted into
  a ticket or a chat without leaking a credential.
* A malformed line is recorded by its number only, never by its content:
  a line without ``=`` is most likely a secret pasted without its key.
* Unexpected input is a finding, not an exception. Both files are
  external input; a broken line must reach the analyst as a warning, never
  as a traceback (which would also dump locals holding the file text).
* The contract is the ``.env.example`` itself: an empty value there means
  "required", a filled value means "optional, ``Settings`` has a default".
  Keys are compared case-insensitively, mirroring ``case_sensitive=False``
  in ``Settings``.
* Legacy ``OLLAMA_*`` names are a fixed table mirroring the
  ``AliasChoices`` in ``Settings``, so a v1.0.0 ``.env`` passes with
  warnings instead of false "missing" errors. Canonical spelling wins over
  the alias, in the same order ``AliasChoices`` resolves them.
* Type and range validation stays in ``Settings``; this module checks
  presence, emptiness and naming only.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

_COMMENT_PREFIX: Final = "#"
_EXPORT_PREFIX: Final = "export "
_ENCLOSING_QUOTES: Final = ('"', "'")
_KEY_VALUE_RE: Final = re.compile(r"(?P<key>[A-Za-z_][A-Za-z0-9_]*)=(?P<value>.*)")

_LEGACY_ALIASES: Final[Mapping[str, str]] = {
    "OLLAMA_API_KEY": "LLM_API_KEY",
    "OLLAMA_MODEL": "LLM_MODEL",
    "OLLAMA_BASE_URL": "LLM_BASE_URL",
}
"""Legacy (v1.0.0) env name -> canonical name, mirroring ``Settings``' ``AliasChoices``.

Kept as a fixed table rather than derived from ``Settings`` so this module
stays free of pydantic internals; ``tests/test_envcheck.py`` guards the
mirror against drift.
"""


class FindingKind(StrEnum):
    """What an :class:`EnvFinding` reports about a key or a line."""

    MISSING = "missing"
    EMPTY = "empty"
    UNKNOWN = "unknown"
    LEGACY = "legacy"
    DUPLICATE = "duplicate"
    MALFORMED = "malformed"


class FindingSeverity(StrEnum):
    """Whether a finding blocks (``error``) or merely warns.

    Named ``FindingSeverity`` to avoid colliding with the LLM-assigned
    :class:`lst.schemas.Severity` of triage events.
    """

    ERROR = "error"
    WARNING = "warning"


class CheckedFile(StrEnum):
    """Which of the two input files a finding refers to."""

    ENV = "env"
    EXAMPLE = "example"


_SEVERITY_BY_KIND: Final[Mapping[FindingKind, FindingSeverity]] = {
    FindingKind.MISSING: FindingSeverity.ERROR,
    FindingKind.EMPTY: FindingSeverity.ERROR,
    FindingKind.UNKNOWN: FindingSeverity.WARNING,
    FindingKind.LEGACY: FindingSeverity.WARNING,
    FindingKind.DUPLICATE: FindingSeverity.WARNING,
    FindingKind.MALFORMED: FindingSeverity.WARNING,
}

_SEVERITY_LABEL_PT: Final[Mapping[FindingSeverity, str]] = {
    FindingSeverity.ERROR: "ERRO",
    FindingSeverity.WARNING: "AVISO",
}

_IN_EXAMPLE_FILE_PT: Final = " no arquivo de exemplo"
_OF_EXAMPLE_FILE_PT: Final = " do arquivo de exemplo"


@dataclass(frozen=True)
class DotenvEntry:
    """One key of a dotenv file after duplicate resolution.

    Attributes:
        key: Key spelling as written on the effective (last) line.
        value: Effective value, stripped and unquoted. Kept only so the
            checker can test for emptiness; it is never rendered.
        lines: 1-based numbers of every line defining this key, in file
            order. More than one line means the key is duplicated and the
            last one wins (dotenv semantics).
    """

    key: str
    value: str
    lines: tuple[int, ...]

    @property
    def line(self) -> int:
        """Return the line whose value is effective (the last occurrence)."""
        return self.lines[-1]

    @property
    def is_duplicated(self) -> bool:
        """Return whether the key appears on more than one line."""
        return len(self.lines) > 1

    @property
    def is_empty(self) -> bool:
        """Return whether the effective value is the empty string."""
        return self.value == ""


@dataclass(frozen=True)
class ParsedDotenv:
    """Structured view of one dotenv file.

    Attributes:
        entries: One entry per distinct key (case-insensitive), in order
            of first appearance.
        malformed_lines: 1-based numbers of lines that are neither blank,
            comment nor ``KEY=value``. Numbers only, by design.
    """

    entries: tuple[DotenvEntry, ...]
    malformed_lines: tuple[int, ...]

    def find(self, key: str) -> DotenvEntry | None:
        """Return the entry for ``key`` (case-insensitive), or ``None`` when absent.

        Args:
            key: Key name in any casing.

        Returns:
            The matching :class:`DotenvEntry`, or ``None`` if the file
            does not define the key. Absence is a normal outcome here,
            not a failure.
        """
        wanted = _normalise_key(key)
        for entry in self.entries:
            if _normalise_key(entry.key) == wanted:
                return entry
        return None


@dataclass(frozen=True)
class EnvFinding:
    """One problem found while checking the ``.env``.

    Attributes:
        kind: What was found; the severity follows from it.
        key: Key spelling as written in the file it came from. ``None``
            only for :attr:`FindingKind.MALFORMED`, where no key exists.
        lines: 1-based lines involved. Empty for a required key that is
            absent; every occurrence for a duplicate; one line otherwise.
        file: Which input file the line numbers refer to. Key-based
            findings are always about the ``.env``; ``duplicate`` and
            ``malformed`` may come from the example file too.
    """

    kind: FindingKind
    key: str | None
    lines: tuple[int, ...]
    file: CheckedFile = CheckedFile.ENV

    @property
    def severity(self) -> FindingSeverity:
        """Return the severity implied by :attr:`kind`."""
        return _SEVERITY_BY_KIND[self.kind]


@dataclass(frozen=True)
class EnvReport:
    """Outcome of :func:`check_env`.

    Not a pipeline-stage contract, so a frozen dataclass is enough; the
    Pydantic schemas in :mod:`lst.schemas` stay reserved for the pipeline.

    Attributes:
        findings: Every finding, in report order: contract keys first
            (missing / empty), then ``.env`` keys (legacy / unknown), then
            parse findings of the ``.env`` and finally of the example file.
        checked_key_count: Number of distinct keys the contract defines.
    """

    findings: tuple[EnvFinding, ...]
    checked_key_count: int

    @property
    def error_count(self) -> int:
        """Return how many findings have error severity."""
        return sum(finding.severity is FindingSeverity.ERROR for finding in self.findings)

    @property
    def warning_count(self) -> int:
        """Return how many findings have warning severity."""
        return sum(finding.severity is FindingSeverity.WARNING for finding in self.findings)

    @property
    def ok(self) -> bool:
        """Return whether the ``.env`` can be used as-is (no error findings)."""
        return self.error_count == 0


def parse_dotenv(text: str) -> ParsedDotenv:
    """Parse dotenv text into keys, effective values and malformed line numbers.

    Rules: blank lines and lines whose first non-blank character is ``#``
    are skipped; an ``export `` prefix is dropped; a valid line is
    ``KEY=value`` with ``KEY`` matching ``[A-Za-z_][A-Za-z0-9_]*``, the
    value being everything after the first ``=``, stripped, minus one pair
    of enclosing quotes. Anything else is malformed and recorded by line
    number only. Keys repeat case-insensitively; the last one wins.

    Args:
        text: Full content of a dotenv file. Any string is accepted.

    Returns:
        A :class:`ParsedDotenv`; this function never raises.

    Example:
        >>> parsed = parse_dotenv('export LLM_MODEL="fake-model"\\noops\\n')
        >>> (parsed.entries[0].key, parsed.entries[0].value, parsed.malformed_lines)
        ('LLM_MODEL', 'fake-model', (2,))
    """
    entries_by_key: dict[str, DotenvEntry] = {}
    malformed_lines: list[int] = []

    # split("\n") rather than splitlines(): the latter also breaks on form
    # feeds and Unicode separators, which would desynchronise the reported
    # numbers from what the analyst sees in an editor.
    for line_number, raw_line in enumerate(text.split("\n"), start=1):
        line = raw_line.strip()
        if not line or line.startswith(_COMMENT_PREFIX):
            continue
        if line.startswith(_EXPORT_PREFIX):
            line = line.removeprefix(_EXPORT_PREFIX).lstrip()

        matched = _KEY_VALUE_RE.fullmatch(line)
        if matched is None:
            malformed_lines.append(line_number)
            continue

        key = matched.group("key")
        value = _strip_enclosing_quotes(matched.group("value").strip())
        previous = entries_by_key.get(_normalise_key(key))
        earlier_lines = previous.lines if previous is not None else ()
        entries_by_key[_normalise_key(key)] = DotenvEntry(
            key=key,
            value=value,
            lines=(*earlier_lines, line_number),
        )

    return ParsedDotenv(
        entries=tuple(entries_by_key.values()),
        malformed_lines=tuple(malformed_lines),
    )


def check_env(example_text: str, env_text: str) -> EnvReport:
    """Compare a ``.env`` against the ``.env.example`` contract.

    Args:
        example_text: Content of the contract file. An empty value marks
            the key as required; a filled value marks it as optional.
        env_text: Content of the local ``.env``.

    Returns:
        An :class:`EnvReport`; its :attr:`EnvReport.ok` is ``True`` when no
        finding has error severity. Values from either file never reach
        the report.

    Example:
        >>> report = check_env("LLM_API_KEY=\\nLLM_MODEL=x\\n", "LLM_API_KEY=fake-key\\n")
        >>> (report.ok, report.checked_key_count, report.findings)
        (True, 2, ())
    """
    contract = parse_dotenv(example_text)
    env = parse_dotenv(env_text)

    findings: list[EnvFinding] = []
    findings.extend(_check_contract_keys(contract, env))
    findings.extend(_check_env_keys(contract, env))
    findings.extend(_parse_findings(env, CheckedFile.ENV))
    findings.extend(_parse_findings(contract, CheckedFile.EXAMPLE))

    return EnvReport(findings=tuple(findings), checked_key_count=len(contract.entries))


def render_report(report: EnvReport) -> str:
    """Render an :class:`EnvReport` as pt-BR text: one line per finding plus a summary.

    Args:
        report: Outcome of :func:`check_env`.

    Returns:
        Lines joined by ``\\n`` (no trailing newline). Only key names and
        line numbers appear -- never values.

    Example:
        >>> print(render_report(check_env("LLM_API_KEY=\\n", "")))
        [ERRO] LLM_API_KEY: obrigatória e ausente
        1 erro(s), 0 aviso(s)
    """
    lines = [
        f"[{_SEVERITY_LABEL_PT[finding.severity]}] {_describe(finding)}"
        for finding in report.findings
    ]
    lines.append(_summary_line(report))
    return "\n".join(lines)


def _normalise_key(key: str) -> str:
    """Return the case-insensitive comparison form of a key (ASCII upper-case)."""
    return key.upper()


def _strip_enclosing_quotes(value: str) -> str:
    """Remove one pair of matching ``"`` or ``'`` quotes wrapping ``value``, if present."""
    is_quoted = len(value) >= 2 and value[0] == value[-1] and value[0] in _ENCLOSING_QUOTES
    return value[1:-1] if is_quoted else value


def _legacy_alias_of(canonical_key: str) -> str | None:
    """Return the legacy env name for ``canonical_key``, or ``None`` if it has none."""
    wanted = _normalise_key(canonical_key)
    return next(
        (alias for alias, canonical in _LEGACY_ALIASES.items() if canonical == wanted),
        None,
    )


def _resolve_effective_entry(env: ParsedDotenv, canonical_key: str) -> DotenvEntry | None:
    """Return the ``.env`` entry that ``Settings`` would read for ``canonical_key``.

    The canonical spelling wins even when empty, because ``AliasChoices``
    stops at the first name present -- an empty ``LLM_API_KEY`` next to a
    filled ``OLLAMA_API_KEY`` still fails validation.
    """
    canonical_entry = env.find(canonical_key)
    if canonical_entry is not None:
        return canonical_entry
    legacy_name = _legacy_alias_of(canonical_key)
    return env.find(legacy_name) if legacy_name is not None else None


def _check_contract_keys(contract: ParsedDotenv, env: ParsedDotenv) -> list[EnvFinding]:
    """Flag contract keys that are missing (required) or empty in the ``.env``."""
    findings: list[EnvFinding] = []
    for contract_entry in contract.entries:
        is_required = contract_entry.is_empty
        effective = _resolve_effective_entry(env, contract_entry.key)
        if effective is None:
            if is_required:
                findings.append(EnvFinding(FindingKind.MISSING, key=contract_entry.key, lines=()))
        elif effective.is_empty:
            kind = FindingKind.MISSING if is_required else FindingKind.EMPTY
            findings.append(EnvFinding(kind, key=effective.key, lines=(effective.line,)))
    return findings


def _check_env_keys(contract: ParsedDotenv, env: ParsedDotenv) -> list[EnvFinding]:
    """Flag ``.env`` keys that are legacy aliases or unknown to the contract."""
    findings: list[EnvFinding] = []
    for entry in env.entries:
        if _normalise_key(entry.key) in _LEGACY_ALIASES:
            findings.append(EnvFinding(FindingKind.LEGACY, key=entry.key, lines=(entry.line,)))
        elif contract.find(entry.key) is None:
            findings.append(EnvFinding(FindingKind.UNKNOWN, key=entry.key, lines=(entry.line,)))
    return findings


def _parse_findings(parsed: ParsedDotenv, file: CheckedFile) -> list[EnvFinding]:
    """Turn a file's duplicate keys and malformed lines into findings."""
    findings = [
        EnvFinding(FindingKind.DUPLICATE, key=entry.key, lines=entry.lines, file=file)
        for entry in parsed.entries
        if entry.is_duplicated
    ]
    findings.extend(
        EnvFinding(FindingKind.MALFORMED, key=None, lines=(line_number,), file=file)
        for line_number in parsed.malformed_lines
    )
    return findings


def _describe(finding: EnvFinding) -> str:
    """Return the pt-BR body of a finding line (after the ``[ERRO]``/``[AVISO]`` tag)."""
    where = _format_lines(finding.lines)
    is_in_example = finding.file is CheckedFile.EXAMPLE

    if finding.key is None:
        # Malformed line: the number is all the analyst gets, on purpose --
        # the content may be a secret pasted without its key.
        of_file = _OF_EXAMPLE_FILE_PT if is_in_example else ""
        return f"{where}{of_file}: malformada (ignorada)"
    if finding.kind is FindingKind.MISSING and not finding.lines:
        return f"{finding.key}: obrigatória e ausente"
    if finding.kind is FindingKind.MISSING:
        return f"{finding.key}: obrigatória e vazia ({where})"
    if finding.kind is FindingKind.EMPTY:
        return f"{finding.key}: vazia — preencha ou remova a linha para usar o padrão ({where})"
    if finding.kind is FindingKind.UNKNOWN:
        return f"{finding.key}: chave desconhecida ({where})"
    if finding.kind is FindingKind.LEGACY:
        preferred = _LEGACY_ALIASES[_normalise_key(finding.key)]
        return f"{finding.key}: nome legado — prefira {preferred}"
    in_file = _IN_EXAMPLE_FILE_PT if is_in_example else ""
    return f"{finding.key}: chave repetida{in_file} ({where}) — a última vale"


def _format_lines(lines: tuple[int, ...]) -> str:
    """Return ``linha 9`` / ``linhas 3 e 9`` / ``linhas 3, 5 e 9``; empty for no lines."""
    if not lines:
        return ""
    if len(lines) == 1:
        return f"linha {lines[0]}"
    leading = ", ".join(str(line_number) for line_number in lines[:-1])
    return f"linhas {leading} e {lines[-1]}"


def _summary_line(report: EnvReport) -> str:
    """Return the closing summary: ``OK`` with the key count, or the error/warning tally."""
    if not report.findings:
        return f"OK: {report.checked_key_count} chaves conferidas, sem problemas"
    return f"{report.error_count} erro(s), {report.warning_count} aviso(s)"
