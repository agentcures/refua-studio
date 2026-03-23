from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from collections.abc import Mapping
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _duration_ms(start_iso: str, end_iso: str) -> int | None:
    try:
        start = datetime.fromisoformat(start_iso)
        end = datetime.fromisoformat(end_iso)
    except ValueError:
        return None
    delta = end - start
    return max(int(delta.total_seconds() * 1000), 0)


def _timestamp_key(value: Any) -> float:
    if not isinstance(value, str) or not value:
        return 0.0
    try:
        return datetime.fromisoformat(value).timestamp()
    except ValueError:
        return 0.0


def _clean_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _clean_mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): item for key, item in value.items()}


def _clean_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return round(float(value), 2)
    if isinstance(value, str):
        try:
            return round(float(value.strip()), 2)
        except ValueError:
            return None
    return None


def _candidate_key(candidate: Mapping[str, Any], index: int) -> str:
    for field_name in ("cure_id", "drug_id", "name", "smiles"):
        value = _clean_text(candidate.get(field_name))
        if value is not None:
            return value
    tool = _clean_text(candidate.get("tool")) or "candidate"
    return f"{tool}:{index}"


def _canonical_drug_name(candidate: Mapping[str, Any], drug_id: str) -> str:
    return _clean_text(candidate.get("name")) or drug_id


def build_promising_drug_snapshot(jobs: list[dict[str, Any]]) -> dict[str, Any]:
    aggregated: dict[str, dict[str, Any]] = {}
    source_job_ids: set[str] = set()
    observation_count = 0

    for job in jobs:
        result = job.get("result")
        if not isinstance(result, Mapping):
            continue

        candidates = result.get("promising_cures")
        if not isinstance(candidates, list):
            continue

        job_id = _clean_text(job.get("job_id")) or "unknown-job"
        job_kind = _clean_text(job.get("kind")) or "unknown"
        discovered_at = (
            _clean_text(job.get("updated_at"))
            or _clean_text(job.get("created_at"))
            or ""
        )
        request_payload = job.get("request")
        request_objective = None
        if isinstance(request_payload, Mapping):
            request_objective = _clean_text(request_payload.get("objective"))
        objective = request_objective or _clean_text(result.get("objective"))

        for index, raw_candidate in enumerate(candidates):
            if not isinstance(raw_candidate, Mapping):
                continue

            observation_count += 1
            source_job_ids.add(job_id)

            drug_id = _candidate_key(raw_candidate, index)
            score = _clean_float(raw_candidate.get("score")) or 0.0
            promising = bool(raw_candidate.get("promising"))
            tool = _clean_text(raw_candidate.get("tool")) or "unknown"
            timestamp = _timestamp_key(discovered_at)
            metrics = _clean_mapping(raw_candidate.get("metrics"))
            admet = _clean_mapping(raw_candidate.get("admet"))
            evidence_paths = _clean_mapping(raw_candidate.get("evidence_paths"))
            tool_args = _clean_mapping(raw_candidate.get("tool_args"))
            source = {
                "job_id": job_id,
                "job_kind": job_kind,
                "discovered_at": discovered_at,
                "objective": objective,
                "tool": tool,
                "score": score,
                "promising": promising,
            }

            entry = aggregated.get(drug_id)
            if entry is None:
                entry = {
                    "drug_id": drug_id,
                    "name": _canonical_drug_name(raw_candidate, drug_id),
                    "target": _clean_text(raw_candidate.get("target")),
                    "smiles": _clean_text(raw_candidate.get("smiles")),
                    "tool": tool,
                    "tools": set([tool]),
                    "score": score,
                    "promising": promising,
                    "assessment": _clean_text(raw_candidate.get("assessment")),
                    "metrics": metrics,
                    "admet": admet,
                    "evidence_paths": evidence_paths,
                    "tool_args": tool_args,
                    "first_seen_at": discovered_at,
                    "latest_seen_at": discovered_at,
                    "seen_count": 0,
                    "promising_runs": 0,
                    "source_jobs": set(),
                    "sources": [],
                    "_best_rank": (1 if promising else 0, score, timestamp),
                    "_latest_timestamp": timestamp,
                    "_first_timestamp": timestamp or float("inf"),
                }
                aggregated[drug_id] = entry

            entry["seen_count"] = int(entry["seen_count"]) + 1
            if promising:
                entry["promising_runs"] = int(entry["promising_runs"]) + 1
                entry["promising"] = True

            entry["tools"].add(tool)
            entry["source_jobs"].add(job_id)
            entry["sources"].append(source)

            latest_timestamp = float(entry["_latest_timestamp"])
            if timestamp >= latest_timestamp:
                entry["_latest_timestamp"] = timestamp
                entry["latest_seen_at"] = discovered_at or entry["latest_seen_at"]

            first_timestamp = float(entry["_first_timestamp"])
            if timestamp and timestamp <= first_timestamp:
                entry["_first_timestamp"] = timestamp
                entry["first_seen_at"] = discovered_at or entry["first_seen_at"]

            candidate_rank = (1 if promising else 0, score, timestamp)
            if candidate_rank >= entry["_best_rank"]:
                entry["_best_rank"] = candidate_rank
                entry["score"] = score
                entry["tool"] = tool
                entry["name"] = _canonical_drug_name(raw_candidate, drug_id)
                entry["target"] = (
                    _clean_text(raw_candidate.get("target")) or entry["target"]
                )
                entry["smiles"] = (
                    _clean_text(raw_candidate.get("smiles")) or entry["smiles"]
                )
                entry["assessment"] = (
                    _clean_text(raw_candidate.get("assessment")) or entry["assessment"]
                )
                if metrics:
                    entry["metrics"] = metrics
                if admet:
                    entry["admet"] = admet
                if evidence_paths:
                    entry["evidence_paths"] = evidence_paths
                if tool_args:
                    entry["tool_args"] = tool_args

    drugs: list[dict[str, Any]] = []
    targets: set[str] = set()
    tools: set[str] = set()

    for entry in aggregated.values():
        entry["tools"] = sorted(str(item) for item in entry["tools"] if item)
        entry["source_jobs_count"] = len(entry["source_jobs"])
        entry["sources"].sort(
            key=lambda item: (
                _timestamp_key(item.get("discovered_at")),
                float(item.get("score") or 0.0),
            ),
            reverse=True,
        )
        entry.pop("_best_rank", None)
        entry.pop("_latest_timestamp", None)
        entry.pop("_first_timestamp", None)
        entry.pop("source_jobs", None)
        drugs.append(entry)

        target = _clean_text(entry.get("target"))
        if target is not None:
            targets.add(target)
        for tool_name in entry.get("tools", []):
            cleaned_tool = _clean_text(tool_name)
            if cleaned_tool is not None:
                tools.add(cleaned_tool)

    drugs.sort(
        key=lambda item: (
            not bool(item.get("promising")),
            -float(item.get("score") or 0.0),
            -int(item.get("seen_count") or 0),
            -_timestamp_key(item.get("latest_seen_at")),
            str(item.get("name") or item.get("drug_id") or "").lower(),
        )
    )

    promising_count = sum(1 for item in drugs if bool(item.get("promising")))
    return {
        "drugs": drugs,
        "summary": {
            "total_drugs": len(drugs),
            "promising_count": promising_count,
            "watchlist_count": max(len(drugs) - promising_count, 0),
            "source_jobs_count": len(source_job_ids),
            "total_observations": observation_count,
        },
        "facets": {
            "targets": sorted(targets),
            "tools": sorted(tools),
        },
    }


class JobStore:
    """SQLite-backed job metadata store."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path, timeout=30.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with closing(self._connect()) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    status TEXT NOT NULL,
                    cancel_requested INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    progress_json TEXT,
                    result_json TEXT,
                    error_text TEXT
                )
                """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_jobs_updated ON jobs(updated_at DESC)"
            )
            columns = {
                str(row["name"])
                for row in conn.execute("PRAGMA table_info(jobs)").fetchall()
            }
            if "cancel_requested" not in columns:
                conn.execute(
                    "ALTER TABLE jobs ADD COLUMN cancel_requested INTEGER NOT NULL DEFAULT 0"
                )
            if "progress_json" not in columns:
                conn.execute("ALTER TABLE jobs ADD COLUMN progress_json TEXT")
            conn.commit()

    def create_job(self, *, kind: str, request: dict[str, Any]) -> dict[str, Any]:
        job_id = str(uuid.uuid4())
        now = _utc_now_iso()
        with self._lock, closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO jobs(
                    job_id, kind, status, cancel_requested, created_at, updated_at,
                    request_json, progress_json, result_json, error_text
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    kind,
                    "queued",
                    0,
                    now,
                    now,
                    json.dumps(request, ensure_ascii=True),
                    None,
                    None,
                    None,
                ),
            )
            conn.commit()
        job = self.get_job(job_id)
        if job is None:
            raise RuntimeError("Failed to create job.")
        return job

    def set_running(self, job_id: str) -> bool:
        return self._set_status(
            job_id,
            status="running",
            allow_from=("queued",),
        )

    def set_completed(self, job_id: str, result: dict[str, Any]) -> bool:
        return self._set_status(
            job_id,
            status="completed",
            result=result,
            error=None,
            cancel_requested=False,
            allow_from=("running",),
        )

    def set_failed(self, job_id: str, error: str) -> bool:
        return self._set_status(
            job_id,
            status="failed",
            result=None,
            error=error,
            cancel_requested=False,
            allow_from=("running",),
        )

    def set_cancelled(self, job_id: str, reason: str = "Cancelled by user.") -> bool:
        return self._set_status(
            job_id,
            status="cancelled",
            result=None,
            error=reason,
            cancel_requested=True,
            allow_from=("queued", "running"),
        )

    def request_cancel(
        self,
        job_id: str,
        *,
        reason: str = "Cancellation requested by user.",
    ) -> bool:
        now = _utc_now_iso()
        with self._lock, closing(self._connect()) as conn:
            cursor = conn.execute(
                """
                UPDATE jobs
                SET cancel_requested = 1,
                    updated_at = ?,
                    error_text = COALESCE(error_text, ?)
                WHERE job_id = ? AND status = 'running'
                """,
                (now, reason, job_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def is_cancel_requested(self, job_id: str) -> bool:
        with self._lock, closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT cancel_requested FROM jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
        if row is None:
            return False
        return bool(int(row["cancel_requested"]))

    def _set_status(
        self,
        job_id: str,
        *,
        status: str,
        result: dict[str, Any] | None = None,
        error: str | None = None,
        cancel_requested: bool | None = None,
        allow_from: tuple[str, ...] | None = None,
    ) -> bool:
        now = _utc_now_iso()
        result_json = (
            json.dumps(result, ensure_ascii=True) if result is not None else None
        )
        cancel_requested_value = (
            1 if cancel_requested else 0 if cancel_requested is not None else None
        )
        with self._lock, closing(self._connect()) as conn:
            if cancel_requested_value is None:
                set_clause = "status = ?, updated_at = ?, result_json = ?, error_text = ?"
                values: tuple[Any, ...] = (status, now, result_json, error)
            else:
                set_clause = (
                    "status = ?, updated_at = ?, result_json = ?, error_text = ?, cancel_requested = ?"
                )
                values = (
                    status,
                    now,
                    result_json,
                    error,
                    cancel_requested_value,
                )
            if allow_from:
                placeholders = ",".join("?" for _ in allow_from)
                cursor = conn.execute(
                    f"""
                    UPDATE jobs
                    SET {set_clause}
                    WHERE job_id = ? AND status IN ({placeholders})
                    """,
                    (*values, job_id, *allow_from),
                )
            else:
                cursor = conn.execute(
                    f"""
                    UPDATE jobs
                    SET {set_clause}
                    WHERE job_id = ?
                    """,
                    (*values, job_id),
                )
            conn.commit()
            return cursor.rowcount > 0

    def update_progress(self, job_id: str, progress: dict[str, Any] | None) -> bool:
        progress_json = (
            json.dumps(progress, ensure_ascii=True) if progress is not None else None
        )
        now = _utc_now_iso()
        with self._lock, closing(self._connect()) as conn:
            cursor = conn.execute(
                """
                UPDATE jobs
                SET updated_at = ?, progress_json = ?
                WHERE job_id = ? AND status = 'running'
                """,
                (now, progress_json, job_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self._lock, closing(self._connect()) as conn:
            row = conn.execute(
                """
                SELECT job_id, kind, status, created_at, updated_at,
                       cancel_requested, request_json, progress_json, result_json, error_text
                FROM jobs
                WHERE job_id = ?
                """,
                (job_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_job(row)

    def list_jobs(
        self,
        *,
        limit: int = 100,
        statuses: tuple[str, ...] | None = None,
    ) -> list[dict[str, Any]]:
        safe_limit = min(max(limit, 1), 1000)
        with self._lock, closing(self._connect()) as conn:
            if statuses:
                placeholders = ",".join("?" for _ in statuses)
                rows = conn.execute(
                    f"""
                    SELECT job_id, kind, status, created_at, updated_at,
                           cancel_requested, request_json, progress_json, result_json, error_text
                    FROM jobs
                    WHERE status IN ({placeholders})
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (*statuses, safe_limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT job_id, kind, status, created_at, updated_at,
                           cancel_requested, request_json, progress_json, result_json, error_text
                    FROM jobs
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (safe_limit,),
                ).fetchall()
        return [self._row_to_job(row) for row in rows]

    def clear_jobs(self, *, statuses: tuple[str, ...]) -> int:
        if not statuses:
            raise ValueError("statuses must not be empty")
        with self._lock, closing(self._connect()) as conn:
            placeholders = ",".join("?" for _ in statuses)
            cursor = conn.execute(
                f"DELETE FROM jobs WHERE status IN ({placeholders})",
                tuple(statuses),
            )
            conn.commit()
            return int(cursor.rowcount)

    def list_promising_drugs(self, *, limit: int = 300) -> dict[str, Any]:
        jobs = self.list_jobs(limit=limit, statuses=("completed",))
        return build_promising_drug_snapshot(jobs)

    def status_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        with self._lock, closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) AS count FROM jobs GROUP BY status"
            ).fetchall()
        for row in rows:
            counts[str(row["status"])] = int(row["count"])
        return counts

    @staticmethod
    def _row_to_job(row: sqlite3.Row) -> dict[str, Any]:
        request_json = row["request_json"]
        progress_json = row["progress_json"]
        result_json = row["result_json"]
        created_at = row["created_at"]
        updated_at = row["updated_at"]
        request = json.loads(request_json) if isinstance(request_json, str) else {}
        progress = (
            json.loads(progress_json) if isinstance(progress_json, str) else None
        )
        result = json.loads(result_json) if isinstance(result_json, str) else None
        return {
            "job_id": row["job_id"],
            "kind": row["kind"],
            "status": row["status"],
            "cancel_requested": bool(int(row["cancel_requested"])),
            "created_at": created_at,
            "updated_at": updated_at,
            "duration_ms": _duration_ms(created_at, updated_at),
            "request": request,
            "progress": progress,
            "result": result,
            "error": row["error_text"],
        }
