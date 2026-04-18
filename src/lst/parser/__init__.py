"""Parser + Template Miner stage.

Converts raw log files into a small set of ``LogTemplate`` objects by
pairing a streaming file reader with drain3's online template miner.

Public surface:

* ``mine_templates`` -- the stage's single entry point.
* ``iter_log_lines`` -- the lazy reader, exposed for ad-hoc use and
  testing.
"""

from lst.parser.reader import iter_log_lines
from lst.parser.template_miner import mine_templates

__all__ = ["iter_log_lines", "mine_templates"]
