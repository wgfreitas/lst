"""Reporter stage: turn ``list[ExplainedEvent]`` into a Markdown report.

The Reporter is the terminal stage of the LST pipeline. It consumes the
already-explained events and emits a single Markdown string in pt-BR,
ready to be written to disk, piped into ``less``, or attached to a SOC
ticket. No I/O, no logging, no network: rendering is a pure function so
tests assert on the exact bytes the analyst will read.

Only :func:`render` is part of the public surface; the helper functions
in :mod:`lst.reporter.markdown` are deliberately module-private so the
Reporter's output contract stays small and stable.
"""

from lst.reporter.markdown import render

__all__ = ["render"]
