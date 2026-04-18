"""Per-line DTO bridging the Parser and the Aggregator.

The Parser emits a :class:`~lst.schemas.LogTemplate` per drain3 cluster
but only retains three sample lines per cluster for memory reasons. The
Aggregator, on the other hand, needs per-line primitives (timestamps,
extracted IPs, extracted usernames) to compute window statistics and
cardinalities. ``MinedLine`` is the narrow record that carries exactly
those primitives from one stage to the next.

The module name starts with an underscore to signal "internal layout"
-- the canonical import is ``from lst.parser import MinedLine``.
"""

from __future__ import annotations

from typing import Annotated, ClassVar

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
)

from lst.schemas import IpAddressStr

Username = Annotated[
    str,
    StringConstraints(min_length=1, max_length=64, strip_whitespace=True),
]
"""A non-empty stripped username -- shape, not semantics, is checked."""


class MinedLine(BaseModel):
    """One raw log line paired with its drain3 cluster and extracted tokens.

    Attributes:
        cluster_id: drain3 cluster identifier the line was routed into
            (>= 1, matches :attr:`LogTemplate.cluster_id`).
        timestamp: UTC-aware timestamp parsed from the line (or a
            ``datetime.now(UTC)`` fallback when the line had no
            recognisable timestamp).
        extracted_ips: Zero or more IPv4 literals found in the raw line.
            Each entry is validated as an IP via
            :func:`ipaddress.ip_address` at construction time.
        extracted_users: Zero or more usernames captured by the Parser's
            keyword heuristics (``for``, ``user``, ``by user``,
            ``for user``).

    Example:
        MinedLine(
            cluster_id=1,
            timestamp=datetime(2026, 4, 18, 10, 0, 1, tzinfo=UTC),
            extracted_ips=["203.0.113.10"],
            extracted_users=["root"],
        )
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(
        frozen=True,
        str_strip_whitespace=True,
    )

    cluster_id: int = Field(..., ge=1, strict=True)
    timestamp: AwareDatetime
    extracted_ips: list[IpAddressStr] = Field(default_factory=list)
    extracted_users: list[Username] = Field(default_factory=list)
