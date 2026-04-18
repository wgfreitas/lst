"""Contract satisfied by every deterministic rule in the Detector.

The Detector engine iterates over a list of objects that honour the
:class:`Rule` Protocol. Using :class:`typing.Protocol` rather than an
abstract base class keeps each rule a plain, instantiable class (no
mandatory ``super().__init__`` boilerplate) while still giving mypy
enough information to catch signature drift across rules.

Contract summary:

* ``name`` -- rule identifier written to :attr:`FlaggedEvent.rule_name`.
  Must be globally unique across :data:`ACTIVE_RULES`; the engine
  relies on it for reporting, not for dedup (dedup keys on
  ``cluster_id``).
* ``category`` -- the broad :class:`FlagCategory` this rule produces.
  Two rules may share a category; the engine's tie-break uses it.
* ``description_pt`` -- one-line pt-BR description of what the rule
  catches. Lives on the rule (not on the Reporter) so adding a rule
  never requires editing a translation table elsewhere -- the Reporter
  just iterates :data:`ACTIVE_RULES`.
* ``evaluate`` -- pure function from an :class:`AggregatedTemplate` to
  an optional :class:`FlaggedEvent`. Returning ``None`` means "no
  match". Rules must be side-effect-free (no I/O, no logging) so
  reordering has no observable effect.
"""

from __future__ import annotations

from typing import Protocol

from lst.schemas import AggregatedTemplate, FlagCategory, FlaggedEvent


class Rule(Protocol):
    """Protocol every deterministic detection rule must implement."""

    name: str
    category: FlagCategory
    description_pt: str

    def evaluate(self, aggregated: AggregatedTemplate) -> FlaggedEvent | None:
        """Return a :class:`FlaggedEvent` if this rule fires, else ``None``.

        Implementations must be pure (no I/O, no mutation of ``aggregated``)
        and must not raise on well-formed input -- a rule that cannot make
        a decision should return ``None`` rather than propagating.
        """
        ...
