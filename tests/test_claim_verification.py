from __future__ import annotations

from als_intel.webui import _verify_cited_claim_ids


def test_verify_cited_claim_ids_rejects_unknown_ids() -> None:
    synthesis = {
        "mentioned_claim_ids": ["C_VALID", "C_MISSING"],
        "supporting_claim_ids": ["C_MISSING"],
    }
    evidence_rows = [
        {"claim_id": "C_VALID", "claim_text": "valid claim text"},
    ]
    guarded, flags = _verify_cited_claim_ids(synthesis=synthesis, evidence_rows=evidence_rows)
    assert guarded["mentioned_claim_ids"] == ["C_VALID"]
    assert guarded["supporting_claim_ids"] == []
    assert "invalid_claim_id:C_MISSING" in flags
