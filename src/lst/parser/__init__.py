"""Parser + Template Miner stage.

Converts raw log files into a pair ``(list[LogTemplate], list[MinedLine])``
by combining a streaming file reader with drain3's online template miner
and per-line IP/user extraction.

Public surface:

* :func:`mine_templates` -- the stage's entry point; returns both the
  cluster summaries and the per-line DTOs the Aggregator consumes.
* :func:`iter_log_lines` -- the lazy reader, exposed for ad-hoc use and
  testing.
* :class:`MinedLine` -- the per-line DTO. Re-exported from a private
  submodule so ``from lst.parser import MinedLine`` is the canonical
  import path.
"""

from lst.parser._mined_line import MinedLine
from lst.parser.reader import iter_log_lines
from lst.parser.template_miner import mine_templates

__all__ = ["MinedLine", "iter_log_lines", "mine_templates"]
