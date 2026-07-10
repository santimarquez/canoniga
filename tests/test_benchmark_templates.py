from __future__ import annotations

import json
from pathlib import Path

from als_intel.benchmark_templates import scaffold_benchmark_templates


def test_scaffold_benchmark_templates_creates_family_files(tmp_path: Path) -> None:
    result = scaffold_benchmark_templates(str(tmp_path / "templates"))
    families = result["files"]["families"]

    for family_name in ["grounding", "contradiction", "uncertainty", "actionability"]:
        p = Path(str(families[family_name]))
        assert p.exists()
        first_line = p.read_text(encoding="utf-8").splitlines()[0]
        row = json.loads(first_line)
        assert row["metadata"]["family"] == family_name

    guide = Path(str(result["files"]["guide"]))
    assert guide.exists()
