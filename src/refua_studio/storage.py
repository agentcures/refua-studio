from __future__ import annotations

import json
import sqlite3
import threading
import uuid
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
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    result_json TEXT,
                    error_text TEXT
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_jobs_updated ON jobs(updated_at DESC)"
            )
            conn.commit()

    def create_job(self, *, kind: str, request: dict[str, Any]) -> dict[str, Any]:
        job_id = str(uuid.uuid4())
        now = _utc_now_iso()
        with self._lock, closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO jobs(
                    job_id, kind, status, created_at, updated_at,
                    request_json, result_json, error_text
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    kind,
                    "queued",
                    now,
                    now,
                    json.dumps(request, ensure_ascii=True),
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
            allow_from=("running",),
        )

    def set_failed(self, job_id: str, error: str) -> bool:
        return self._set_status(
            job_id,
            status="failed",
            result=None,
            error=error,
            allow_from=("running",),
        )

    def set_cancelled(self, job_id: str, reason: str = "Cancelled by user.") -> bool:
        return self._set_status(
            job_id,
            status="cancelled",
            result=None,
            error=reason,
            allow_from=("queued",),
        )

    def _set_status(
        self,
        job_id: str,
        *,
        status: str,
        result: dict[str, Any] | None = None,
        error: str | None = None,
        allow_from: tuple[str, ...] | None = None,
    ) -> bool:
        now = _utc_now_iso()
        result_json = json.dumps(result, ensure_ascii=True) if result is not None else None
        with self._lock, closing(self._connect()) as conn:
            if allow_from:
                placeholders = ",".join("?" for _ in allow_from)
                cursor = conn.execute(
                    f"""
                    UPDATE jobs
                    SET status = ?, updated_at = ?, result_json = ?, error_text = ?
                    WHERE job_id = ? AND status IN ({placeholders})
                    """,
                    (status, now, result_json, error, job_id, *allow_from),
                )
            else:
                cursor = conn.execute(
                    """
                    UPDATE jobs
                    SET status = ?, updated_at = ?, result_json = ?, error_text = ?
                    WHERE job_id = ?
                    """,
                    (status, now, result_json, error, job_id),
                )
            conn.commit()
            return cursor.rowcount > 0

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self._lock, closing(self._connect()) as conn:
            row = conn.execute(
                """
                SELECT job_id, kind, status, created_at, updated_at,
                       request_json, result_json, error_text
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
                           request_json, result_json, error_text
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
                           request_json, result_json, error_text
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
        result_json = row["result_json"]
        created_at = row["created_at"]
        updated_at = row["updated_at"]
        request = json.loads(request_json) if isinstance(request_json, str) else {}
        result = json.loads(result_json) if isinstance(result_json, str) else None
        return {
            "job_id": row["job_id"],
            "kind": row["kind"],
            "status": row["status"],
            "created_at": created_at,
            "updated_at": updated_at,
            "duration_ms": _duration_ms(created_at, updated_at),
            "request": request,
            "result": result,
            "error": row["error_text"],
        }
