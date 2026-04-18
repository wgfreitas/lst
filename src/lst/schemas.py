"""Pipeline data contracts.

Defines the Pydantic models that flow between the four stages of the LST
pipeline (Parser -> Aggregator -> Detector -> Explainer) and on to the
Reporter module that emits the final Markdown report.

Design rules enforced here:

* Immutability -- every model is frozen. Stages return new instances
  instead of mutating inputs.
* Composition over inheritance -- later-stage models wrap earlier-stage
  models in a named field (e.g. ``AggregatedTemplate.template``). Rationale:
  composition stays readable when optional fields appear, and it keeps
  test doubles simple.
* UTC-aware datetimes only -- naive ``datetime`` values are rejected via
  ``AwareDatetime``. Rationale: mixing aware and naive datetimes in the
  same pipeline hides off-by-hours bugs in a domain where timelines matter.
* Strict numeric coercion -- numeric fields refuse string input. Rationale:
  loud failure beats silent coercion for security-adjacent code.
* JSON round-trip safe -- ``model_dump_json`` / ``model_validate_json``
  produce equivalent objects, so the Explainer can hand the LLM a stable
  payload without adapter code.
"""

from enum import StrEnum
from ipaddress import ip_address
from typing import Annotated, ClassVar, Self

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)


def _validate_ip_address(value: str) -> str:
    """Return ``value`` unchanged if it parses as an IPv4 or IPv6 address.

    Args:
        value: Candidate IP literal (e.g. ``"192.0.2.10"`` or ``"2001:db8::1"``).

    Returns:
        The input string, unmodified, when it is a valid IP literal.

    Raises:
        ValueError: if ``value`` is not a valid IPv4 or IPv6 literal.
    """
    ip_address(value)
    return value


LogLine = Annotated[str, StringConstraints(min_length=1, max_length=4000)]
"""A single raw log line: non-empty, bounded at 4000 characters."""

IpAddressStr = Annotated[str, AfterValidator(_validate_ip_address)]
"""An IPv4 or IPv6 literal carried as a string (format validated)."""


class FlagCategory(StrEnum):
    """Category of the deterministic rule that flagged a template.

    Values are the canonical identifiers serialised into the LLM prompt and
    the final Markdown report -- changing them is a breaking change.
    """

    NOVELTY = "novelty"
    SPIKE = "spike"
    BRUTE_FORCE = "brute_force"
    HIGH_RISK_PATTERN = "high_risk_pattern"
    VARIETY = "variety"


class Severity(StrEnum):
    """Severity classification assigned by the LLM Explainer.

    The Reporter sorts events by this field, so the ordering must be
    preserved: LOW < MEDIUM < HIGH < CRITICAL (lexicographic on the
    ``StrEnum`` values is not meaningful -- downstream code must rely on
    the declared order or an explicit mapping).
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class LogTemplate(BaseModel):
    """A template mined from raw log lines by drain3.

    Groups N similar log lines under a single parameterized pattern with
    ``<*>`` placeholders. Emitted by the Parser + Template Miner stage.

    Attributes:
        cluster_id: Sequential drain3 cluster identifier (>= 1).
        template: Parameterized pattern text with drain3 placeholders.
        size: Number of log lines matched by this template so far.
        sample_lines: Up to three raw log lines that matched. The cap is
            deliberate: enough context for the LLM Explainer without
            exploding the prompt's token budget.
        first_seen: UTC timestamp of the first matched line. Naive
            datetimes are rejected.
        last_seen: UTC timestamp of the most recent matched line. Must
            not precede ``first_seen``.

    Example:
        LogTemplate(
            cluster_id=1,
            template="Failed password for <*> from <*> port <*>",
            size=3,
            sample_lines=["Failed password for root from 1.2.3.4 port 22"],
            first_seen=datetime(2026, 4, 18, 10, 0, tzinfo=timezone.utc),
            last_seen=datetime(2026, 4, 18, 11, 0, tzinfo=timezone.utc),
        )
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(
        frozen=True,
        str_strip_whitespace=True,
    )

    cluster_id: int = Field(
        ...,
        ge=1,
        strict=True,
        description="Sequential drain3 cluster ID.",
    )
    template: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Parameterized template text with drain3 placeholders.",
    )
    size: int = Field(
        ...,
        ge=1,
        strict=True,
        description="Total log lines matched by this template so far.",
    )
    sample_lines: list[LogLine] = Field(
        ...,
        max_length=3,
        description="Up to three representative original log lines.",
    )
    first_seen: AwareDatetime = Field(
        ...,
        description="UTC timestamp of the first matched line.",
    )
    last_seen: AwareDatetime = Field(
        ...,
        description="UTC timestamp of the most recent matched line.",
    )

    @model_validator(mode="after")
    def _check_invariants(self) -> Self:
        if self.last_seen < self.first_seen:
            raise ValueError("last_seen must not precede first_seen")
        if self.size < len(self.sample_lines):
            raise ValueError("size must be >= len(sample_lines)")
        return self


class AggregatedTemplate(BaseModel):
    """Template enriched with window-level statistics.

    Produced by the Aggregator stage after a second pass over the templates
    emitted by the Parser. Holds rates, cardinalities, and representative
    samples of IPs and usernames extracted from the ``<*>`` positions.

    Attributes:
        template: The underlying ``LogTemplate`` -- composition, not
            inheritance.
        total_count: Total occurrences in the analysed window. Must be
            >= ``template.size`` (the Aggregator may see more lines than
            the Parser emitted if the template matured mid-stream).
        rate_per_minute: Mean occurrences per minute across
            ``[first_seen, last_seen]``.
        peak_rate_per_minute: Maximum occurrences in any single one-minute
            window. Always >= ``rate_per_minute``.
        unique_ips: Distinct IP addresses captured from ``<*>`` positions.
        unique_users: Distinct usernames captured from ``<*>`` positions.
        sample_ips: Up to five representative IPs. Each entry is validated
            as an IPv4 or IPv6 literal.
        sample_users: Up to five representative usernames.

    Example:
        AggregatedTemplate(
            template=log_template,
            total_count=42,
            rate_per_minute=0.7,
            peak_rate_per_minute=2.5,
            unique_ips=3,
            unique_users=2,
            sample_ips=["1.2.3.4", "5.6.7.8"],
            sample_users=["root", "admin"],
        )
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(
        frozen=True,
        str_strip_whitespace=True,
    )

    template: LogTemplate = Field(
        ...,
        description="The underlying template emitted by the Parser.",
    )
    total_count: int = Field(
        ...,
        ge=1,
        strict=True,
        description="Total occurrences in the analysed window.",
    )
    rate_per_minute: float = Field(
        ...,
        ge=0.0,
        strict=True,
        description="Mean occurrences per minute across the window.",
    )
    peak_rate_per_minute: float = Field(
        ...,
        ge=0.0,
        strict=True,
        description="Maximum occurrences seen in any one-minute window.",
    )
    unique_ips: int = Field(
        ...,
        ge=0,
        strict=True,
        description="Cardinality of distinct IP addresses captured.",
    )
    unique_users: int = Field(
        ...,
        ge=0,
        strict=True,
        description="Cardinality of distinct usernames captured.",
    )
    sample_ips: list[IpAddressStr] = Field(
        ...,
        max_length=5,
        description="Up to five representative IPs (IPv4 or IPv6 literal).",
    )
    sample_users: list[str] = Field(
        ...,
        max_length=5,
        description="Up to five representative usernames.",
    )

    @model_validator(mode="after")
    def _check_invariants(self) -> Self:
        if self.peak_rate_per_minute < self.rate_per_minute:
            raise ValueError("peak_rate_per_minute must be >= rate_per_minute")
        if self.total_count < self.template.size:
            raise ValueError("total_count must be >= template.size")
        if len(self.sample_ips) > self.unique_ips:
            raise ValueError("len(sample_ips) must be <= unique_ips")
        if len(self.sample_users) > self.unique_users:
            raise ValueError("len(sample_users) must be <= unique_users")
        return self


class FlaggedEvent(BaseModel):
    """An aggregated template that a deterministic rule flagged as suspect.

    Produced by the Detector stage. Carries the rule identity and a
    normalised confidence score in ``[0.0, 1.0]``.

    Attributes:
        aggregated: The underlying ``AggregatedTemplate`` -- composition.
        category: Broad class of the rule that flagged the event.
        rule_name: Canonical rule identifier (e.g. ``brute_force_v1``).
        score: Detector confidence in ``[0.0, 1.0]``.
        triggered_at: UTC timestamp when the rule fired.
        context_notes: Optional free-form notes the Explainer prompt can
            include as extra context.

    Example:
        FlaggedEvent(
            aggregated=aggregated_template,
            category=FlagCategory.BRUTE_FORCE,
            rule_name="brute_force_v1",
            score=0.85,
            triggered_at=datetime(2026, 4, 18, 11, 5, tzinfo=timezone.utc),
            context_notes="3 IPs hit 42 times in 1h",
        )
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(
        frozen=True,
        str_strip_whitespace=True,
    )

    aggregated: AggregatedTemplate = Field(
        ...,
        description="The underlying aggregated template.",
    )
    category: FlagCategory = Field(
        ...,
        description="Broad class of the rule that flagged the event.",
    )
    rule_name: str = Field(
        ...,
        min_length=1,
        max_length=80,
        description="Canonical rule identifier.",
    )
    score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        strict=True,
        description="Detector confidence in the interval [0.0, 1.0].",
    )
    triggered_at: AwareDatetime = Field(
        ...,
        description="UTC timestamp when the rule fired.",
    )
    context_notes: str | None = Field(
        default=None,
        max_length=500,
        description="Optional free-form notes used by the Explainer prompt.",
    )


class ExplainedEvent(BaseModel):
    """A flagged event enriched with the LLM's analysis.

    Produced by the LLM Explainer stage -- the final object consumed by
    the Reporter. Carries the pt-BR explanation, a severity class, a
    suggested next action, and light auditing metadata.

    Attributes:
        flagged: The underlying ``FlaggedEvent`` -- composition.
        explanation: Explanation written by the LLM, in pt-BR.
        severity: Severity class chosen by the LLM.
        next_action: Short, actionable recommendation in pt-BR.
        llm_model: Identifier of the model that generated the analysis
            (e.g. ``gpt-oss:120b``). Kept for auditing.
        llm_latency_ms: Response latency in milliseconds (>= 0).
        explained_at: UTC timestamp when the analysis was produced.

    Example:
        ExplainedEvent(
            flagged=flagged_event,
            explanation="Tentativa de brute-force com múltiplos IPs...",
            severity=Severity.HIGH,
            next_action="Bloquear os IPs ofensivos no firewall.",
            llm_model="gpt-oss:120b",
            llm_latency_ms=1240,
            explained_at=datetime(2026, 4, 18, 11, 5, tzinfo=timezone.utc),
        )
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(
        frozen=True,
        str_strip_whitespace=True,
    )

    flagged: FlaggedEvent = Field(
        ...,
        description="The underlying flagged event.",
    )
    explanation: str = Field(
        ...,
        min_length=10,
        max_length=2000,
        description="Explanation written by the LLM, in pt-BR.",
    )
    severity: Severity = Field(
        ...,
        description="Severity class chosen by the LLM.",
    )
    next_action: str = Field(
        ...,
        min_length=5,
        max_length=500,
        description="Short, actionable recommendation in pt-BR.",
    )
    llm_model: str = Field(
        ...,
        min_length=1,
        max_length=120,
        description="Identifier of the LLM that produced the analysis.",
    )
    llm_latency_ms: int = Field(
        ...,
        ge=0,
        strict=True,
        description="LLM response latency in milliseconds.",
    )
    explained_at: AwareDatetime = Field(
        ...,
        description="UTC timestamp when the analysis was produced.",
    )
