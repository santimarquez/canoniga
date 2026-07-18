from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from als_intel.manual_sync import (
    ManualSyncError,
    cooldown_remaining_seconds,
    get_manual_sync_status,
    load_updatable_sources,
    start_manual_sync,
)
from als_intel.store import EvidenceStore


def _record_recent_manual_success(db_path: Path, scope: str, *, hours_ago: float = 1.0) -> None:
    store = EvidenceStore(db_path)
    store.init_db()
    completed_at = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()
    store.record_manual_sync_success(scope, completed_at=completed_at)


def test_load_updatable_sources_reflects_plan_jobs(tmp_path: Path) -> None:
    db_path = tmp_path / "als.sqlite"
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(
        '[{"source":"pubmed","query":"als","max_results":1},{"source":"ctgov","query":"als","max_results":1}]',
        encoding="utf-8",
    )
    sources = load_updatable_sources(db_path=str(db_path), plan_path=str(plan_path))
    names = [str(row["source"]) for row in sources]
    assert set(names) == {"pubmed", "ctgov"}
    assert names == sorted(names, key=lambda source: str(sources[names.index(source)]["display_name"]).lower())


def test_load_updatable_sources_marks_failed_recent_attempt(tmp_path: Path) -> None:
    db_path = tmp_path / "als.sqlite"
    store = EvidenceStore(db_path)
    store.init_db()
    plan_path = tmp_path / "plan.json"
    plan_path.write_text('[{"source":"chembl","query":"als","max_results":1}]', encoding="utf-8")

    old_success = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    recent_failed = datetime.now(timezone.utc).isoformat()
    with store._connect() as conn:
        conn.execute(
            """
            INSERT INTO sync_state (
                source_name, last_successful_timestamp, failure_count, updated_at, last_sync_timestamp
            ) VALUES ('chembl', ?, 1, ?, ?)
            """,
            (old_success, recent_failed, old_success),
        )
        conn.execute(
            """
            INSERT INTO sync_runs (
                source_name, query, started_at, ended_at, status, notes
            ) VALUES ('chembl', 'als', ?, ?, 'failed', 'interrupted')
            """,
            (recent_failed, recent_failed),
        )
        conn.commit()

    sources = load_updatable_sources(db_path=str(db_path), plan_path=str(plan_path))
    chembl = sources[0]
    assert chembl["source"] == "chembl"
    assert chembl["sync_status"] == "failed"
    assert str(chembl["last_successful_at"]).startswith(old_success[:10])
    assert str(chembl["last_attempt_at"]).startswith(recent_failed[:10])


def test_load_updatable_sources_sorts_least_updated_first(tmp_path: Path) -> None:
    db_path = tmp_path / "als.sqlite"
    store = EvidenceStore(db_path)
    store.init_db()
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(
        '[{"source":"pubmed","query":"als","max_results":1},{"source":"ctgov","query":"als","max_results":1},{"source":"chembl","query":"als","max_results":1}]',
        encoding="utf-8",
    )

    old_time = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    recent_time = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    with store._connect() as conn:
        conn.execute(
            """
            INSERT INTO sync_state (source_name, last_successful_timestamp, failure_count, updated_at)
            VALUES ('pubmed', ?, 0, ?), ('ctgov', ?, 0, ?)
            """,
            (recent_time, recent_time, old_time, old_time),
        )
        conn.commit()

    sources = load_updatable_sources(db_path=str(db_path), plan_path=str(plan_path))
    names = [str(row["source"]) for row in sources]
    assert names == ["chembl", "ctgov", "pubmed"]


def test_cooldown_blocks_recent_all_scope_sync(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "als.sqlite"
    plan = "config/sync_plan.smoke_public_sources.json"
    _record_recent_manual_success(db_path, "all", hours_ago=1.0)
    # All individual sources are also on cooldown → Sync All must stay disabled.
    import json

    for source in [str(job["source"]) for job in json.loads(Path(plan).read_text(encoding="utf-8"))]:
        _record_recent_manual_success(db_path, source, hours_ago=1.0)
    monkeypatch.setenv("ALS_MANUAL_SYNC_COOLDOWN_HOURS", "6")
    store = EvidenceStore(db_path)
    assert cooldown_remaining_seconds(store, "all") > 0
    status = get_manual_sync_status(db_path=str(db_path), plan_path=plan)
    assert status["can_trigger_all"] is False


def test_sync_all_enabled_when_source_never_synced_despite_all_cooldown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "als.sqlite"
    plan = "config/sync_plan.smoke_public_sources.json"
    _record_recent_manual_success(db_path, "all", hours_ago=1.0)
    _record_recent_manual_success(db_path, "pubmed", hours_ago=1.0)
    monkeypatch.setenv("ALS_MANUAL_SYNC_COOLDOWN_HOURS", "6")
    status = get_manual_sync_status(db_path=str(db_path), plan_path=plan)
    # Never-synced sources remain eligible, so Sync All stays enabled.
    assert status["can_trigger_all"] is True
    assert any(
        row["sync_status"] == "never" and bool(row["can_trigger"])
        for row in status["sources"]
    )


def test_cooldown_blocks_recent_source_sync(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "als.sqlite"
    _record_recent_manual_success(db_path, "pubmed", hours_ago=1.0)
    monkeypatch.setenv("ALS_MANUAL_SYNC_COOLDOWN_HOURS", "6")
    store = EvidenceStore(db_path)
    assert cooldown_remaining_seconds(store, "pubmed") > 0
    status = get_manual_sync_status(db_path=str(db_path), plan_path="config/sync_plan.smoke_public_sources.json")
    pubmed = next(row for row in status["sources"] if row["source"] == "pubmed")
    ctgov = next(row for row in status["sources"] if row["source"] == "ctgov")
    assert pubmed["can_trigger"] is False
    assert ctgov["can_trigger"] is True
    assert status["can_trigger_all"] is True


def test_cooldown_allows_old_sync(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "als.sqlite"
    _record_recent_manual_success(db_path, "all", hours_ago=7.0)
    monkeypatch.setenv("ALS_MANUAL_SYNC_COOLDOWN_HOURS", "6")
    store = EvidenceStore(db_path)
    assert cooldown_remaining_seconds(store, "all") == 0
    status = get_manual_sync_status(db_path=str(db_path), plan_path="config/sync_plan.smoke_public_sources.json")
    assert status["can_trigger_all"] is True


def test_failed_manual_sync_does_not_apply_cooldown(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "als.sqlite"
    store = EvidenceStore(db_path)
    store.init_db()
    monkeypatch.setenv("ALS_MANUAL_SYNC_COOLDOWN_HOURS", "6")

    def _failing_job(db_path: str, job: dict[str, object]) -> dict[str, object]:
        return {
            "status": "failed",
            "source": str(job["source"]),
            "run_id": 99,
            "inserted": 0,
            "updated": 0,
            "unchanged": 0,
            "notes": "boom",
        }

    monkeypatch.setattr("als_intel.manual_sync._run_single_job", _failing_job)
    start_manual_sync(
        db_path=str(db_path),
        scope="pubmed",
        triggered_by="usr_test",
        plan_path="config/sync_plan.smoke_public_sources.json",
    )

    import time

    deadline = time.time() + 2.0
    while time.time() < deadline:
        status = get_manual_sync_status(db_path=str(db_path), plan_path="config/sync_plan.smoke_public_sources.json")
        if not status["in_progress"]:
            break
        time.sleep(0.05)

    assert cooldown_remaining_seconds(store, "pubmed") == 0
    pubmed = next(row for row in status["sources"] if row["source"] == "pubmed")
    assert pubmed["can_trigger"] is True
    assert status["last_completion_status"] == "failed"
    assert "boom" in str(status["last_completion_error"])
    audit_events = status.get("audit_events")
    assert isinstance(audit_events, list)
    assert audit_events
    assert audit_events[0]["status"] == "failed"


def test_start_manual_sync_rejects_during_cooldown(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "als.sqlite"
    plan = "config/sync_plan.smoke_public_sources.json"
    import json

    _record_recent_manual_success(db_path, "all", hours_ago=2.0)
    for source in [str(job["source"]) for job in json.loads(Path(plan).read_text(encoding="utf-8"))]:
        _record_recent_manual_success(db_path, source, hours_ago=2.0)
    monkeypatch.setenv("ALS_MANUAL_SYNC_COOLDOWN_HOURS", "6")
    with pytest.raises(ManualSyncError) as exc:
        start_manual_sync(
            db_path=str(db_path),
            scope="all",
            triggered_by="usr_test",
            plan_path=plan,
        )
    assert exc.value.status_code == 429


def test_start_manual_sync_all_allows_never_synced_during_all_cooldown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "als.sqlite"
    plan = "config/sync_plan.smoke_public_sources.json"
    _record_recent_manual_success(db_path, "all", hours_ago=2.0)
    _record_recent_manual_success(db_path, "pubmed", hours_ago=2.0)
    monkeypatch.setenv("ALS_MANUAL_SYNC_COOLDOWN_HOURS", "6")
    synced: list[str] = []

    def _fake_run_single_job(db_path: str, job: dict[str, object]) -> dict[str, object]:
        source = str(job["source"])
        synced.append(source)
        return {
            "status": "ok",
            "source": source,
            "run_id": len(synced),
            "inserted": 0,
            "updated": 0,
            "unchanged": 0,
            "notes": "",
        }

    monkeypatch.setattr("als_intel.manual_sync._run_single_job", _fake_run_single_job)
    started = start_manual_sync(
        db_path=str(db_path),
        scope="all",
        triggered_by="usr_test",
        plan_path=plan,
    )
    assert started["status"] == "started"

    import time

    deadline = time.time() + 3.0
    while time.time() < deadline:
        status = get_manual_sync_status(db_path=str(db_path), plan_path=plan)
        if not status["in_progress"]:
            break
        time.sleep(0.05)

    assert "pubmed" not in synced
    assert synced
    assert status["last_completion_status"] == "success"


def test_start_manual_sync_starts_background_job(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "als.sqlite"
    store = EvidenceStore(db_path)
    store.init_db()

    def _fake_run_single_job(db_path: str, job: dict[str, object]) -> dict[str, object]:
        return {
            "status": "ok",
            "source": str(job["source"]),
            "inserted": 0,
            "updated": 0,
            "unchanged": 0,
            "notes": "",
        }

    monkeypatch.setattr("als_intel.manual_sync._run_single_job", _fake_run_single_job)

    started = start_manual_sync(
        db_path=str(db_path),
        scope="pubmed",
        triggered_by="usr_test",
        plan_path="config/sync_plan.smoke_public_sources.json",
    )
    assert started["status"] == "started"
    assert started["scope"] == "pubmed"

    import time

    deadline = time.time() + 2.0
    while time.time() < deadline:
        status = get_manual_sync_status(db_path=str(db_path), plan_path="config/sync_plan.smoke_public_sources.json")
        if not status["in_progress"]:
            break
        time.sleep(0.05)
    assert status["in_progress"] is False
    assert status["last_completion_status"] == "success"
    assert store.manual_sync_last_successful_at("pubmed") is not None
    audit_events = status.get("audit_events")
    assert isinstance(audit_events, list)
    assert audit_events
    assert audit_events[0]["status"] == "success"


def test_manual_sync_honors_unbounded_plan_max_results(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import als_intel.manual_sync as manual_sync_module

    captured: list[int] = []

    def _capture_job(db_path: str, job: dict[str, object]) -> dict[str, object]:
        captured.append(manual_sync_module._resolve_manual_sync_max_results(job))
        return {
            "status": "ok",
            "source": str(job["source"]),
            "run_id": 1,
            "inserted": 0,
            "updated": 0,
            "unchanged": 0,
            "notes": "",
        }

    monkeypatch.setattr("als_intel.manual_sync._run_single_job", _capture_job)
    plan_path = tmp_path / "plan.json"
    plan_path.write_text('[{"source":"fda_labels","query":"als","max_results":0}]', encoding="utf-8")
    db_path = tmp_path / "als.sqlite"
    start_manual_sync(
        db_path=str(db_path),
        scope="fda_labels",
        triggered_by="usr_test",
        plan_path=str(plan_path),
    )

    import time

    deadline = time.time() + 2.0
    while time.time() < deadline:
        status = get_manual_sync_status(db_path=str(db_path), plan_path=str(plan_path))
        if not status["in_progress"]:
            break
        time.sleep(0.05)

    assert captured == [0]


def test_evidence_reads_continue_while_sync_run_is_running(tmp_path: Path) -> None:
    db_path = tmp_path / "als.sqlite"
    store = EvidenceStore(db_path)
    store.init_db()
    from als_intel.models import EvidenceRecord

    store.upsert_evidence(
        EvidenceRecord(
            claim_id="C1",
            claim_text="test",
            disease="ALS",
            entity="entity",
            relation="modulates",
            outcome="outcome",
            effect_direction="supports",
            study_type="observational",
            sample_size=10,
            endpoint_validity=0.5,
            replication_count=0,
            peer_reviewed=True,
            year=2024,
            source_title="title",
            source_doi="10.1/c1",
        ),
        score_breakdown={
            "study": 0.1,
            "sample": 0.1,
            "replication": 0.1,
            "peer_review": 0.1,
            "endpoint": 0.1,
            "source": 0.1,
            "extraction": 0.1,
            "total": 0.5,
        },
        source_score=0.5,
    )
    store.start_sync_run(source_name="fda_labels", query="als")
    rows = store.all_evidence()
    assert len(rows) == 1


def test_start_manual_sync_rejects_unknown_source(tmp_path: Path) -> None:
    db_path = tmp_path / "als.sqlite"
    with pytest.raises(ManualSyncError) as exc:
        start_manual_sync(
            db_path=str(db_path),
            scope="not_a_real_source",
            triggered_by="usr_test",
            plan_path="config/sync_plan.smoke_public_sources.json",
        )
    assert exc.value.status_code == 404


def test_reconcile_stale_sync_runs_clears_orphaned_running_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "als.sqlite"
    store = EvidenceStore(db_path)
    store.init_db()
    run_id = store.start_sync_run(source_name="pubmed", query="als")
    assert store.has_running_sync_run() is True
    reconciled = store.reconcile_stale_sync_runs(worker_active=False)
    assert reconciled == 1
    assert store.has_running_sync_run() is False
    with store._connect() as conn:
        row = conn.execute("SELECT status, notes FROM sync_runs WHERE id = ?", (run_id,)).fetchone()
    assert row is not None
    assert str(row[0]) == "failed"
    assert "interrupted" in str(row[1]).lower()


def test_get_manual_sync_status_clears_stale_running_without_worker(tmp_path: Path) -> None:
    db_path = tmp_path / "als.sqlite"
    store = EvidenceStore(db_path)
    store.init_db()
    store.start_sync_run(source_name="pubmed", query="als")
    status = get_manual_sync_status(
        db_path=str(db_path),
        plan_path="config/sync_plan.smoke_public_sources.json",
    )
    assert status["manual_sync_active"] is False
    assert status["in_progress"] is False
    assert int(status.get("reconciled_stale_runs", 0) or 0) >= 1


def test_get_manual_sync_status_includes_progress_percent(tmp_path: Path) -> None:
    import als_intel.manual_sync as manual_sync_module

    manual_sync_module._MANUAL_SYNC_STATE.update(
        {
            "in_progress": True,
            "scope": "pubmed",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "current_source": "pubmed",
            "current_source_started_at": datetime.now(timezone.utc).isoformat(),
            "completed_sources": 0,
            "total_sources": 1,
            "observed_durations": {},
            "error": None,
        }
    )
    try:
        status = get_manual_sync_status(
            db_path=str(tmp_path / "als.sqlite"),
            plan_path="config/sync_plan.smoke_public_sources.json",
        )
        assert status["manual_sync_active"] is True
        assert status["in_progress"] is True
        assert int(status["progress_percent"]) > 0
        assert int(status["estimated_remaining_seconds"]) >= 0
        assert status["estimated_completion_at"]
    finally:
        manual_sync_module._MANUAL_SYNC_STATE.update(
            {
                "in_progress": False,
                "scope": None,
                "started_at": None,
                "current_source": None,
                "current_source_started_at": None,
                "completed_sources": 0,
                "total_sources": 0,
                "observed_durations": {},
                "error": None,
            }
        )


def test_record_manual_sync_source_duration_updates_running_average(tmp_path: Path) -> None:
    db_path = tmp_path / "als.sqlite"
    store = EvidenceStore(db_path)
    store.init_db()
    store.record_manual_sync_source_duration("pubmed", 100.0)
    store.record_manual_sync_source_duration("pubmed", 200.0)
    assert store.get_source_duration_estimate("pubmed") == 150.0


def test_progress_estimate_recalculates_after_observed_duration(tmp_path: Path) -> None:
    import als_intel.manual_sync as manual_sync_module

    db_path = tmp_path / "als.sqlite"
    store = EvidenceStore(db_path)
    store.init_db()
    store.record_manual_sync_source_duration("pubmed", 60.0)
    store.record_manual_sync_source_duration("ctgov", 120.0)

    started_at = datetime.now(timezone.utc) - timedelta(seconds=30)
    manual_sync_module._MANUAL_SYNC_STATE.update(
        {
            "in_progress": True,
            "scope": "all",
            "started_at": started_at.isoformat(),
            "current_source": "ctgov",
            "current_source_started_at": (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat(),
            "completed_sources": 1,
            "total_sources": 2,
            "observed_durations": {"pubmed": 60.0},
            "error": None,
        }
    )
    try:
        status = get_manual_sync_status(
            db_path=str(db_path),
            plan_path="config/sync_plan.smoke_public_sources.json",
        )
        assert int(status["progress_percent"]) >= 5
        assert int(status["estimated_remaining_seconds"]) > 0
    finally:
        manual_sync_module._MANUAL_SYNC_STATE.update(
            {
                "in_progress": False,
                "scope": None,
                "started_at": None,
                "current_source": None,
                "current_source_started_at": None,
                "completed_sources": 0,
                "total_sources": 0,
                "observed_durations": {},
                "error": None,
            }
        )


def test_start_manual_sync_rejects_concurrent_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "als.sqlite"
    store = EvidenceStore(db_path)
    store.init_db()
    store.start_sync_run(source_name="pubmed", query="als")
    monkeypatch.setattr("als_intel.manual_sync.manual_sync_worker_active", lambda: True)

    with pytest.raises(ManualSyncError) as exc:
        start_manual_sync(
            db_path=str(db_path),
            scope="pubmed",
            triggered_by="usr_test",
            plan_path="config/sync_plan.smoke_public_sources.json",
        )
    assert exc.value.status_code == 409
