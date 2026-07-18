from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from als_intel.scheduler import load_sync_plan, run_scheduled_sync
from als_intel.store import SOURCE_DISPLAY_NAMES, EvidenceStore
from als_intel.sync import run_incremental_sync

DEFAULT_SYNC_PLAN_PATH = "config/sync_plan.all_public_sources.json"
DEFAULT_COOLDOWN_HOURS = 6
MANUAL_SYNC_SCOPE_ALL = "all"
DEFAULT_SOURCE_DURATION_SECONDS = 120.0

logger = logging.getLogger(__name__)

_MANUAL_SYNC_LOCK = threading.Lock()
_MANUAL_SYNC_STATE: dict[str, Any] = {
    "in_progress": False,
    "scope": None,
    "triggered_by": None,
    "started_at": None,
    "current_source": None,
    "current_source_started_at": None,
    "completed_sources": 0,
    "total_sources": 0,
    "observed_durations": {},
    "error": None,
    "completion_status": None,
    "completion_error": None,
    "completion_at": None,
    "event_id": None,
}


class ManualSyncError(Exception):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def get_plan_path() -> str:
    configured = str(os.getenv("ALS_SYNC_PLAN", DEFAULT_SYNC_PLAN_PATH)).strip()
    return configured or DEFAULT_SYNC_PLAN_PATH


def get_cooldown_hours() -> int:
    raw = str(os.getenv("ALS_MANUAL_SYNC_COOLDOWN_HOURS", str(DEFAULT_COOLDOWN_HOURS))).strip()
    try:
        parsed = int(raw)
    except ValueError:
        parsed = DEFAULT_COOLDOWN_HOURS
    return max(1, min(parsed, 24 * 7))


def _parse_iso_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def cooldown_remaining_seconds(
    store: EvidenceStore,
    scope: str,
    *,
    cooldown_hours: int | None = None,
) -> int:
    hours = get_cooldown_hours() if cooldown_hours is None else max(1, min(int(cooldown_hours), 24 * 7))
    normalized_scope = str(scope).strip().lower() or MANUAL_SYNC_SCOPE_ALL
    latest = store.manual_sync_last_successful_at(normalized_scope)
    parsed = _parse_iso_timestamp(latest)
    if parsed is None:
        return 0
    elapsed = (datetime.now(timezone.utc) - parsed).total_seconds()
    remaining = (hours * 3600) - elapsed
    return max(0, int(remaining))


def next_available_at(
    store: EvidenceStore,
    scope: str,
    *,
    cooldown_hours: int | None = None,
) -> str | None:
    remaining = cooldown_remaining_seconds(store, scope, cooldown_hours=cooldown_hours)
    if remaining <= 0:
        return None
    return (datetime.now(timezone.utc) + timedelta(seconds=remaining)).isoformat()


def manual_sync_worker_active() -> bool:
    with _MANUAL_SYNC_LOCK:
        return bool(_MANUAL_SYNC_STATE.get("in_progress"))


def is_sync_in_progress(store: EvidenceStore) -> bool:
    with _MANUAL_SYNC_LOCK:
        if bool(_MANUAL_SYNC_STATE.get("in_progress")):
            return True
    return store.has_running_sync_run()


def _source_updated_sort_key(row: dict[str, object]) -> tuple[int, float, str]:
    ts = str(row.get("last_successful_at", "") or "").strip()
    display_name = str(row.get("display_name", "") or row.get("source", ""))
    if not ts:
        return (0, 0.0, display_name.lower())
    try:
        parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return (1, parsed.timestamp(), display_name.lower())
    except ValueError:
        return (0, 0.0, display_name.lower())


def _source_sync_status_label(activity: dict[str, object]) -> str:
    last_successful_at = str(activity.get("last_successful_at", "") or "").strip()
    last_attempt_at = str(activity.get("last_attempt_at", "") or "").strip()
    last_attempt_status = str(activity.get("last_attempt_status", "") or "").strip().lower()
    success_ts = _parse_iso_timestamp(last_successful_at)
    attempt_ts = _parse_iso_timestamp(last_attempt_at)
    if last_attempt_status == "failed":
        if success_ts and attempt_ts and success_ts >= attempt_ts:
            return "ok"
        return "failed"
    if last_successful_at:
        return "ok"
    if last_attempt_at:
        return last_attempt_status or "unknown"
    return "never"


def _resolve_manual_sync_max_results(job: dict[str, object]) -> int:
    """Return plan max_results; 0 means unbounded (connectors treat <=0 as no limit)."""
    return max(0, int(job.get("max_results", 20) or 0))


def load_updatable_sources(*, db_path: str, plan_path: str | None = None) -> list[dict[str, object]]:
    store = EvidenceStore(db_path)
    store.init_db()
    resolved_plan = plan_path or get_plan_path()
    jobs = load_sync_plan(resolved_plan)
    state_by_source = {
        str(row.get("source_name", "")).strip().lower(): row
        for row in store.list_sync_states()
    }
    sources: list[dict[str, object]] = []
    for job in jobs:
        source = str(job.get("source", "")).strip().lower()
        if not source:
            continue
        sync_state = state_by_source.get(source, {})
        activity = store.get_source_sync_activity(source)
        remaining = cooldown_remaining_seconds(store, source)
        sources.append(
            {
                "source": source,
                "display_name": SOURCE_DISPLAY_NAMES.get(source, source),
                "query": str(job.get("query", "")),
                "last_successful_at": str(activity.get("last_successful_at", "") or ""),
                "last_attempt_at": str(activity.get("last_attempt_at", "") or ""),
                "last_attempt_status": str(activity.get("last_attempt_status", "") or ""),
                "last_attempt_notes": str(activity.get("last_attempt_notes", "") or ""),
                "last_manual_sync_at": str(activity.get("last_manual_sync_at", "") or ""),
                "sync_status": _source_sync_status_label(activity),
                "failure_count": int(sync_state.get("failure_count", 0) or 0),
                "can_trigger": remaining <= 0,
                "cooldown_remaining_seconds": remaining,
                "next_available_at": next_available_at(store, source),
            }
        )
    sources.sort(key=_source_updated_sort_key)
    return sources


def _progress_percent(*, in_progress: bool, completed_sources: int, total_sources: int) -> int:
    done = max(0, int(completed_sources or 0))
    total = max(0, int(total_sources or 0))
    if not in_progress:
        return 100 if done > 0 and total > 0 else 0
    if total <= 0:
        return 10
    if done >= total:
        return 99
    return min(99, max(5, int(round(((done + 0.5) / total) * 100))))


def _estimate_current_source_seconds(
    *,
    store: EvidenceStore,
    source_name: str,
    current_source_started_at: str | None,
) -> float:
    baseline = store.get_source_duration_estimate(
        source_name,
        default_seconds=DEFAULT_SOURCE_DURATION_SECONDS,
    )
    started = _parse_iso_timestamp(current_source_started_at)
    if started is None:
        return baseline
    elapsed = max(0.0, (datetime.now(timezone.utc) - started).total_seconds())
    return max(baseline, elapsed)


def _compute_sync_progress_estimate(
    *,
    store: EvidenceStore,
    state_snapshot: dict[str, Any],
    plan_path: str | None,
    active: bool,
) -> dict[str, object]:
    if not active:
        return {
            "progress_percent": 0,
            "estimated_remaining_seconds": 0,
            "estimated_completion_at": None,
        }

    started_at = _parse_iso_timestamp(str(state_snapshot.get("started_at") or ""))
    if started_at is None:
        return {
            "progress_percent": 5,
            "estimated_remaining_seconds": int(DEFAULT_SOURCE_DURATION_SECONDS),
            "estimated_completion_at": (
                datetime.now(timezone.utc) + timedelta(seconds=DEFAULT_SOURCE_DURATION_SECONDS)
            ).isoformat(),
        }

    now = datetime.now(timezone.utc)
    elapsed_total = max(0.0, (now - started_at).total_seconds())
    scope = str(state_snapshot.get("scope") or "").strip().lower()
    completed = max(0, int(state_snapshot.get("completed_sources", 0) or 0))
    total = max(0, int(state_snapshot.get("total_sources", 0) or 0))
    current_source = str(state_snapshot.get("current_source") or "").strip().lower()
    current_source_started_at = str(state_snapshot.get("current_source_started_at") or "")
    observed_raw = state_snapshot.get("observed_durations", {})
    observed: dict[str, float] = {}
    if isinstance(observed_raw, dict):
        for key, value in observed_raw.items():
            try:
                observed[str(key).strip().lower()] = max(1.0, float(value))
            except (TypeError, ValueError):
                continue

    estimated_chunks: list[float] = []
    if scope == MANUAL_SYNC_SCOPE_ALL and total > 0:
        resolved_plan = plan_path or get_plan_path()
        jobs = load_sync_plan(resolved_plan)
        source_order = [
            str(job.get("source", "")).strip().lower()
            for job in jobs
            if str(job.get("source", "")).strip()
        ]
        for index, source_name in enumerate(source_order):
            if index < completed:
                estimated_chunks.append(
                    observed.get(source_name)
                    or store.get_source_duration_estimate(
                        source_name,
                        default_seconds=DEFAULT_SOURCE_DURATION_SECONDS,
                    )
                )
            elif current_source and source_name == current_source:
                estimated_chunks.append(
                    _estimate_current_source_seconds(
                        store=store,
                        source_name=source_name,
                        current_source_started_at=current_source_started_at or None,
                    )
                )
            elif index > completed:
                estimated_chunks.append(
                    store.get_source_duration_estimate(
                        source_name,
                        default_seconds=DEFAULT_SOURCE_DURATION_SECONDS,
                    )
                )
    else:
        source_name = current_source or scope
        estimated_chunks.append(
            _estimate_current_source_seconds(
                store=store,
                source_name=source_name,
                current_source_started_at=current_source_started_at or None,
            )
        )

    estimated_total = sum(estimated_chunks)
    if estimated_total <= 0:
        estimated_total = DEFAULT_SOURCE_DURATION_SECONDS

    progress_percent = min(99, max(5, int(round((elapsed_total / estimated_total) * 100))))
    remaining_seconds = max(0.0, estimated_total - elapsed_total)
    return {
        "progress_percent": progress_percent,
        "estimated_remaining_seconds": int(round(remaining_seconds)),
        "estimated_completion_at": (now + timedelta(seconds=remaining_seconds)).isoformat(),
    }


def get_manual_sync_status(*, db_path: str, plan_path: str | None = None) -> dict[str, object]:
    store = EvidenceStore(db_path)
    store.init_db()
    worker_active = manual_sync_worker_active()
    reconciled = store.reconcile_stale_sync_runs(worker_active=worker_active)
    remaining_all = cooldown_remaining_seconds(store, MANUAL_SYNC_SCOPE_ALL)
    in_progress = is_sync_in_progress(store)
    active = manual_sync_worker_active()
    with _MANUAL_SYNC_LOCK:
        state_snapshot = dict(_MANUAL_SYNC_STATE)
    completed = int(state_snapshot.get("completed_sources", 0) or 0)
    total = int(state_snapshot.get("total_sources", 0) or 0)
    sources = load_updatable_sources(db_path=db_path, plan_path=plan_path)
    # Enable Sync All when any source is eligible (e.g. never synced), even if the
    # global "all" cooldown is still active from a prior full sync.
    any_source_triggerable = any(bool(row.get("can_trigger")) for row in sources)
    can_trigger_all = (not in_progress) and any_source_triggerable
    progress = _compute_sync_progress_estimate(
        store=store,
        state_snapshot=state_snapshot,
        plan_path=plan_path,
        active=active,
    )
    return {
        "can_trigger_all": can_trigger_all,
        "can_trigger": can_trigger_all,
        "cooldown_remaining_seconds": remaining_all,
        "next_available_at": next_available_at(store, MANUAL_SYNC_SCOPE_ALL),
        "in_progress": in_progress,
        "manual_sync_active": active,
        "reconciled_stale_runs": reconciled,
        "current_scope": state_snapshot.get("scope"),
        "current_source": state_snapshot.get("current_source"),
        "completed_sources": completed,
        "total_sources": total,
        "progress_percent": progress["progress_percent"],
        "estimated_remaining_seconds": progress["estimated_remaining_seconds"],
        "estimated_completion_at": progress["estimated_completion_at"],
        "latest_sync_at": store.latest_sync_timestamp(),
        "sources": sources,
        "error": state_snapshot.get("error"),
        "last_completion_status": state_snapshot.get("completion_status"),
        "last_completion_error": state_snapshot.get("completion_error"),
        "last_completion_at": state_snapshot.get("completion_at"),
        "last_completion_scope": state_snapshot.get("scope"),
        "audit_events": store.list_manual_sync_events(limit=5),
    }


def _job_for_source(plan_path: str, source: str) -> dict[str, object]:
    normalized = str(source).strip().lower()
    jobs = load_sync_plan(plan_path)
    for job in jobs:
        if str(job.get("source", "")).strip().lower() == normalized:
            return job
    raise ManualSyncError(f"Unknown updatable source: {source}", status_code=404)


def _run_single_job(db_path: str, job: dict[str, object]) -> dict[str, object]:
    extractor_config = job.get("extractor_config", {})
    stage_config = job.get("stage_config", {})
    if not isinstance(extractor_config, dict):
        extractor_config = {}
    if not isinstance(stage_config, dict):
        stage_config = {}
    return run_incremental_sync(
        db_path=db_path,
        source=str(job["source"]),
        query=str(job["query"]),
        max_results=_resolve_manual_sync_max_results(job),
        from_file=str(job["from_file"]) if job.get("from_file") else None,
        extractor_config=extractor_config,
        stage_config=stage_config,
    )


def _execute_manual_sync(*, db_path: str, plan_path: str, scope: str, triggered_by: str) -> None:
    global _MANUAL_SYNC_STATE
    store = EvidenceStore(db_path)
    store.init_db()
    event_id: int | None = None
    completion_status = "failed"
    completion_error = ""
    run_ids: list[int] = []
    try:
        event_id = store.start_manual_sync_event(scope=scope, triggered_by=triggered_by)
        with _MANUAL_SYNC_LOCK:
            _MANUAL_SYNC_STATE["event_id"] = event_id
        if scope == "all":
            jobs = [
                job
                for job in load_sync_plan(plan_path)
                if cooldown_remaining_seconds(
                    store,
                    str(job.get("source", "")).strip().lower(),
                )
                <= 0
            ]
            with _MANUAL_SYNC_LOCK:
                _MANUAL_SYNC_STATE["total_sources"] = len(jobs)
                _MANUAL_SYNC_STATE["completed_sources"] = 0
                _MANUAL_SYNC_STATE["observed_durations"] = {}
            if not jobs:
                raise RuntimeError("No sources are currently eligible for sync")
            for index, job in enumerate(jobs):
                source_name = str(job.get("source", "")).strip().lower()
                source_started = datetime.now(timezone.utc)
                with _MANUAL_SYNC_LOCK:
                    _MANUAL_SYNC_STATE["current_source"] = source_name
                    _MANUAL_SYNC_STATE["current_source_started_at"] = source_started.isoformat()
                result = _run_single_job(db_path, job)
                run_id = int(result.get("run_id", 0) or 0)
                if run_id > 0:
                    run_ids.append(run_id)
                if str(result.get("status", "")) != "ok":
                    raise RuntimeError(
                        f"Sync failed for {source_name}: {result.get('notes', 'unknown error')}"
                    )
                duration_seconds = max(
                    1.0,
                    (datetime.now(timezone.utc) - source_started).total_seconds(),
                )
                store.record_manual_sync_source_duration(source_name, duration_seconds)
                store.record_manual_sync_success(source_name)
                with _MANUAL_SYNC_LOCK:
                    observed = dict(_MANUAL_SYNC_STATE.get("observed_durations") or {})
                    observed[source_name] = duration_seconds
                    _MANUAL_SYNC_STATE["observed_durations"] = observed
                    _MANUAL_SYNC_STATE["completed_sources"] = index + 1
        else:
            job = _job_for_source(plan_path, scope)
            source_started = datetime.now(timezone.utc)
            with _MANUAL_SYNC_LOCK:
                _MANUAL_SYNC_STATE["total_sources"] = 1
                _MANUAL_SYNC_STATE["current_source"] = scope
                _MANUAL_SYNC_STATE["current_source_started_at"] = source_started.isoformat()
                _MANUAL_SYNC_STATE["observed_durations"] = {}
            result = _run_single_job(db_path, job)
            run_id = int(result.get("run_id", 0) or 0)
            if run_id > 0:
                run_ids.append(run_id)
            if str(result.get("status", "")) != "ok":
                raise RuntimeError(f"Sync failed for {scope}: {result.get('notes', 'unknown error')}")
            duration_seconds = max(
                1.0,
                (datetime.now(timezone.utc) - source_started).total_seconds(),
            )
            store.record_manual_sync_source_duration(scope, duration_seconds)
            with _MANUAL_SYNC_LOCK:
                _MANUAL_SYNC_STATE["observed_durations"] = {scope: duration_seconds}
                _MANUAL_SYNC_STATE["completed_sources"] = 1
        store.record_manual_sync_success(scope)
        completion_status = "success"
        logger.info(
            "manual_sync_completed scope=%s triggered_by=%s run_ids=%s",
            scope,
            triggered_by,
            run_ids,
        )
    except Exception as exc:
        completion_error = str(exc)
        with _MANUAL_SYNC_LOCK:
            _MANUAL_SYNC_STATE["error"] = completion_error
        logger.exception(
            "manual_sync_failed scope=%s triggered_by=%s run_ids=%s error=%s",
            scope,
            triggered_by,
            run_ids,
            completion_error,
        )
    finally:
        completion_at = datetime.now(timezone.utc).isoformat()
        if event_id is not None:
            store.finish_manual_sync_event(
                event_id,
                status=completion_status,
                error=completion_error,
                run_ids=run_ids,
                notes="manual_sync_worker",
            )
        with _MANUAL_SYNC_LOCK:
            _MANUAL_SYNC_STATE["in_progress"] = False
            _MANUAL_SYNC_STATE["current_source"] = None
            _MANUAL_SYNC_STATE["current_source_started_at"] = None
            _MANUAL_SYNC_STATE["completion_status"] = completion_status
            _MANUAL_SYNC_STATE["completion_error"] = completion_error or _MANUAL_SYNC_STATE.get("error")
            _MANUAL_SYNC_STATE["completion_at"] = completion_at


def start_manual_sync(
    *,
    db_path: str,
    scope: str,
    triggered_by: str,
    plan_path: str | None = None,
) -> dict[str, object]:
    store = EvidenceStore(db_path)
    store.init_db()
    store.reconcile_stale_sync_runs(worker_active=manual_sync_worker_active())
    resolved_plan = plan_path or get_plan_path()
    if not Path(resolved_plan).exists():
        raise ManualSyncError(f"Sync plan not found: {resolved_plan}", status_code=500)

    normalized_scope = str(scope).strip().lower()
    if normalized_scope != "all":
        _job_for_source(resolved_plan, normalized_scope)

    if normalized_scope == MANUAL_SYNC_SCOPE_ALL:
        triggerable = [
            row
            for row in load_updatable_sources(db_path=db_path, plan_path=resolved_plan)
            if bool(row.get("can_trigger"))
        ]
        if not triggerable:
            remaining = cooldown_remaining_seconds(store, MANUAL_SYNC_SCOPE_ALL)
            if remaining > 0:
                raise ManualSyncError(
                    f"Manual sync for all is on cooldown for {remaining} more seconds",
                    status_code=429,
                )
            raise ManualSyncError("No sources are currently eligible for sync", status_code=400)
    else:
        remaining = cooldown_remaining_seconds(store, normalized_scope)
        if remaining > 0:
            raise ManualSyncError(
                f"Manual sync for {normalized_scope} is on cooldown for {remaining} more seconds",
                status_code=429,
            )

    with _MANUAL_SYNC_LOCK:
        if bool(_MANUAL_SYNC_STATE.get("in_progress")) or store.has_running_sync_run():
            raise ManualSyncError("A source sync is already in progress", status_code=409)
        _MANUAL_SYNC_STATE.update(
            {
                "in_progress": True,
                "scope": normalized_scope,
                "triggered_by": triggered_by,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "current_source": None,
                "current_source_started_at": None,
                "completed_sources": 0,
                "total_sources": 0,
                "observed_durations": {},
                "error": None,
                "completion_status": None,
                "completion_error": None,
                "completion_at": None,
                "event_id": None,
            }
        )

    worker = threading.Thread(
        target=_execute_manual_sync,
        kwargs={
            "db_path": db_path,
            "plan_path": resolved_plan,
            "scope": normalized_scope,
            "triggered_by": triggered_by,
        },
        name=f"manual-sync-{normalized_scope}",
        daemon=True,
    )
    worker.start()
    return {
        "status": "started",
        "scope": normalized_scope,
        "plan_path": resolved_plan,
    }


def run_manual_sync_plan_once(*, db_path: str, plan_path: str) -> dict[str, object]:
    """Synchronous helper used in tests."""
    return run_scheduled_sync(
        db_path=db_path,
        plan_file=plan_path,
        cycles=1,
        interval_seconds=0,
    )
