"""Extract the python blocks of a saved model answer into test files.

A block runs from a line with three backticks plus "python" to the next line made only of three
backticks. One block: write it to <dst>. Several blocks: each is preceded by a "### `path`"
heading and is written under <dst_dir>/<path>.
"""

import re
import sys
from pathlib import Path

src = Path(sys.argv[1])
target = Path(sys.argv[2])
lines = src.read_text(encoding="utf-8").splitlines()
blocks, i, heading = [], 0, None
while i < len(lines):
    m = re.match(r"^### `([^`]+\.py)`", lines[i])
    if m:
        heading = m.group(1)
    if lines[i].strip() == "```python":
        j = i + 1
        while lines[j].strip() != "```":
            j += 1
        blocks.append((heading, "\n".join(lines[i + 1 : j]) + "\n"))
        i = j
    i += 1
if len(blocks) == 1:
    target.write_text(blocks[0][1], encoding="utf-8")
    print(target.name, len(blocks[0][1].splitlines()), "linhas")
else:
    for path, code in blocks:
        out = target / path
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(code, encoding="utf-8")
        print(out, len(code.splitlines()), "linhas")
