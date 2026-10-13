"""Merge the model's 'only changed parts' correction into a copy of the P1 v1 suite."""

import re
import sys
from pathlib import Path

base = Path(sys.argv[1]).read_text(encoding="utf-8")
corr = Path(sys.argv[2]).read_text(encoding="utf-8")
corr = corr[corr.index("```python\n") + 10 : corr.rindex("\n```")]
parts = re.split(r"# =+\n# (?:NOVO|SUBSTITUI)[^\n]*\n# =+\n", corr)
_, helpers, corpos, timeout_tests = parts
# 1. helpers before the partitions section
marker = "# " + "=" * 86 + "\n# Partições de equivalência"
assert base.count(marker) == 1
base = base.replace(marker, helpers.strip() + "\n\n\n" + marker)
# 2. replace CORPOS_200_INVALIDOS list
start = base.index("CORPOS_200_INVALIDOS = [")
end = base.index("ERROS_RESPONSE_FORMAT = [")
base = (
    base[:start]
    + corpos.strip().split("CORPOS_200_INVALIDOS = [", 1)[0]
    + "CORPOS_200_INVALIDOS = ["
    + corpos.strip().split("CORPOS_200_INVALIDOS = [", 1)[1]
    + "\n\n"
    + base[end:]
)
# 3. replace the timeout test (decorator + function) with the new block
start = base.index(
    "@pytest.mark.parametrize(\n"
    '    "valor, esperado",\n'
    "    [\n"
    '        pytest.param(None, 60.0, id="padrao"),'
)
end = base.index("def test_base_url_padrao_aponta_para_ollama_cloud")
base = base[:start] + timeout_tests.strip() + "\n\n\n" + base[end:]
Path(sys.argv[3]).write_text(base, encoding="utf-8")
print("ok", len(base.splitlines()), "linhas")
