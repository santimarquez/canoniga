from __future__ import annotations

from als_intel.ingest import load_jsonl
from als_intel.scoring import score_components, source_reliability_score
from als_intel.store import EvidenceStore


def ingest_file(db_path: str, input_file: str) -> int:
    store = EvidenceStore(db_path)
    store.init_db()

    records = load_jsonl(input_file)
    for record in records:
        breakdown = score_components(record)
        source_score = source_reliability_score(record)
        store.upsert_evidence(record, breakdown, source_score)
    return len(records)
