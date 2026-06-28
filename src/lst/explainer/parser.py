"""Parse the LLM's raw reply into a three-field dict.

OpenAI-compatible endpoints (Ollama Cloud, GLM, and others) occasionally
return JSON wrapped in markdown fences, preceded by "Aqui está o JSON:", or
otherwise decorated despite the system prompt asking for none. This
module tolerates those perturbations so the engine can focus on
orchestration, and turns pathological failures into a loud
:class:`ValueError` rather than a silent partial :class:`ExplainedEvent`.

Responsibilities:

1. Strip markdown fences (``\\`\\`\\`json`` / ``\\`\\`\\```) if present.
2. Try a direct :func:`json.loads` first -- the happy path is one call.
3. On failure, extract the first balanced ``{...}`` block via a greedy
   DOTALL regex and retry the decode. The fallback is logged at
   ``WARNING`` so repeated hits surface in operations without breaking
   the current run.
4. Validate that the decoded dict has exactly the three expected keys.
5. Normalise :attr:`severity` to lowercase so case-drift from the model
   does not propagate to downstream ``StrEnum`` comparisons.
"""

from __future__ import annotations

import json
import logging
import re

logger = logging.getLogger(__name__)

_LLM_FIELDS: tuple[str, ...] = ("explanation", "severity", "next_action")

_FENCE_RE = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?```$", re.DOTALL)
_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


def parse_response(raw: str) -> dict[str, str]:
    """Return the validated three-field dict produced by the LLM.

    Args:
        raw: Raw string returned by the chat-completions call. May
            contain markdown fences, preambles, or trailing commentary.

    Returns:
        Dict with exactly the keys ``explanation``, ``severity``, and
        ``next_action``. ``severity`` is lowercased; the other two are
        whitespace-stripped.

    Raises:
        ValueError: if no valid JSON object can be located, or if any
            required field is missing.
    """
    stripped = raw.strip()
    fence_match = _FENCE_RE.match(stripped)
    if fence_match is not None:
        stripped = fence_match.group(1).strip()

    decoded: object
    try:
        decoded = json.loads(stripped)
    except json.JSONDecodeError:
        block = _JSON_BLOCK_RE.search(stripped)
        if block is None:
            raise ValueError("no JSON object found in LLM response") from None
        logger.warning("LLM response required regex fallback to locate JSON body")
        try:
            decoded = json.loads(block.group(0))
        except json.JSONDecodeError as exc:
            raise ValueError(f"JSON block failed to parse: {exc}") from exc

    if not isinstance(decoded, dict):
        raise ValueError(f"expected JSON object, got {type(decoded).__name__}")

    missing = [field for field in _LLM_FIELDS if field not in decoded]
    if missing:
        raise ValueError(f"LLM response missing required fields: {missing}")

    return {
        "explanation": str(decoded["explanation"]).strip(),
        "severity": str(decoded["severity"]).strip().lower(),
        "next_action": str(decoded["next_action"]).strip(),
    }
