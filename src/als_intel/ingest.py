from __future__ import annotations

import json
from pathlib import Path

from als_intel.models import EvidenceRecord


def load_jsonl(file_path: str | Path) -> list[EvidenceRecord]:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Input not found: {path}")

    items: list[EvidenceRecord] = []
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
            items.append(EvidenceRecord.from_dict(payload))
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"Invalid JSONL record at line {index}: {exc}") from exc
    return items
