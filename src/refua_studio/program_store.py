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


class ProgramStore:
    """SQLite-backed store for program graph state and approvals."""

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
                CREATE TABLE IF NOT EXISTS programs (
                    program_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    indication TEXT,
                    target TEXT,
                    stage TEXT,
                    owner TEXT,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS program_events (
                    event_id TEXT PRIMARY KEY,
                    program_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL,
                    source TEXT,
                    run_id TEXT,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS program_approvals (
                    approval_id TEXT PRIMARY KEY,
                    program_id TEXT NOT NULL,
                    gate TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    signer TEXT NOT NULL,
                    signature TEXT NOT NULL,
                    rationale TEXT,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_programs_updated ON programs(updated_at DESC)"
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_program_events_program_created
                ON program_events(program_id, created_at DESC)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_program_approvals_program_created
                ON program_approvals(program_id, created_at DESC)
                """
            )
            conn.commit()

    def upsert_program(
        self,
        *,
        program_id: str | None,
        name: str | None,
        indication: str | None,
        target: str | None,
        stage: str | None,
        owner: str | None,
        metadata: dict[str, Any] | None,
    ) -> dict[str, Any]:
        resolved_program_id = (program_id or "").strip() or str(uuid.uuid4())
        now = _utc_now_iso()
        existing = self.get_program(resolved_program_id)

        if existing is None:
            resolved_name = (name or "").strip() or resolved_program_id
            with self._lock, closing(self._connect()) as conn:
                conn.execute(
                    """
                    INSERT INTO programs(
                        program_id, name, indication, target, stage, owner,
                        metadata_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        resolved_program_id,
                        resolved_name,
                        _normalize_text(indication),
                        _normalize_text(target),
                        _normalize_text(stage),
                        _normalize_text(owner),
                        json.dumps(metadata or {}, ensure_ascii=True),
                        now,
                        now,
                    ),
                )
                conn.commit()
        else:
            resolved_name = _normalize_text(name) or existing["name"]
            with self._lock, closing(self._connect()) as conn:
                conn.execute(
                    """
                    UPDATE programs
                    SET name = ?, indication = ?, target = ?, stage = ?, owner = ?,
                        metadata_json = ?, updated_at = ?
                    WHERE program_id = ?
                    """,
                    (
                        resolved_name,
                        _normalize_text(indication)
                        if indication is not None
                        else existing.get("indication"),
                        _normalize_text(target) if target is not None else existing.get("target"),
                        _normalize_text(stage) if stage is not None else existing.get("stage"),
                        _normalize_text(owner) if owner is not None else existing.get("owner"),
                        json.dumps(
                            metadata if metadata is not None else existing.get("metadata", {}),
                            ensure_ascii=True,
                        ),
                        now,
                        resolved_program_id,
                    ),
                )
                conn.commit()

        refreshed = self.get_program(resolved_program_id)
        if refreshed is None:
            raise RuntimeError("Failed to upsert program")
        return refreshed

    def get_program(self, program_id: str) -> dict[str, Any] | None:
        with self._lock, closing(self._connect()) as conn:
            row = conn.execute(
                """
                SELECT program_id, name, indication, target, stage, owner,
                       metadata_json, created_at, updated_at
                FROM programs
                WHERE program_id = ?
                """,
                (program_id,),
            ).fetchone()
            if row is None:
                return None

            events_count = conn.execute(
                "SELECT COUNT(*) AS c FROM program_events WHERE program_id = ?",
                (program_id,),
            ).fetchone()
            approvals_count = conn.execute(
                "SELECT COUNT(*) AS c FROM program_approvals WHERE program_id = ?",
                (program_id,),
            ).fetchone()

        payload = self._row_to_program(row)
        payload["events_count"] = int(events_count["c"]) if events_count is not None else 0
        payload["approvals_count"] = int(approvals_count["c"]) if approvals_count is not None else 0
        return payload

    def list_programs(
        self,
        *,
        limit: int = 100,
        stage: str | None = None,
    ) -> list[dict[str, Any]]:
        safe_limit = min(max(int(limit), 1), 1000)
        with self._lock, closing(self._connect()) as conn:
            if stage is not None and stage.strip():
                rows = conn.execute(
                    """
                    SELECT program_id, name, indication, target, stage, owner,
                           metadata_json, created_at, updated_at
                    FROM programs
                    WHERE stage = ?
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (stage.strip(), safe_limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT program_id, name, indication, target, stage, owner,
                           metadata_json, created_at, updated_at
                    FROM programs
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (safe_limit,),
                ).fetchall()
        return [self._row_to_program(row) for row in rows]

    def add_event(
        self,
        *,
        program_id: str,
        event_type: str,
        title: str,
        status: str,
        source: str | None,
        run_id: str | None,
        payload: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if self.get_program(program_id) is None:
            raise KeyError(program_id)

        now = _utc_now_iso()
        event_id = str(uuid.uuid4())
        with self._lock, closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO program_events(
                    event_id, program_id, event_type, title, status, source, run_id,
                    payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    program_id,
                    event_type.strip(),
                    title.strip(),
                    status.strip(),
                    _normalize_text(source),
                    _normalize_text(run_id),
                    json.dumps(payload or {}, ensure_ascii=True),
                    now,
                ),
            )
            conn.execute(
                "UPDATE programs SET updated_at = ? WHERE program_id = ?",
                (now, program_id),
            )
            conn.commit()
        event = self.get_event(event_id)
        if event is None:
            raise RuntimeError("Failed to create program event")
        return event

    def get_event(self, event_id: str) -> dict[str, Any] | None:
        with self._lock, closing(self._connect()) as conn:
            row = conn.execute(
                """
                SELECT event_id, program_id, event_type, title, status, source, run_id,
                       payload_json, created_at
                FROM program_events
                WHERE event_id = ?
                """,
                (event_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_event(row)

    def list_events(self, *, program_id: str, limit: int = 200) -> list[dict[str, Any]]:
        safe_limit = min(max(int(limit), 1), 2000)
        with self._lock, closing(self._connect()) as conn:
            rows = conn.execute(
                """
                SELECT event_id, program_id, event_type, title, status, source, run_id,
                       payload_json, created_at
                FROM program_events
                WHERE program_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (program_id, safe_limit),
            ).fetchall()
        return [self._row_to_event(row) for row in rows]

    def has_event_for_run(
        self,
        *,
        program_id: str,
        run_id: str,
        status: str | None = None,
        event_type: str | None = None,
    ) -> bool:
        if not run_id.strip():
            return False
        with self._lock, closing(self._connect()) as conn:
            where = ["program_id = ?", "run_id = ?"]
            params: list[Any] = [program_id, run_id]
            if status is not None and status.strip():
                where.append("status = ?")
                params.append(status.strip())
            if event_type is not None and event_type.strip():
                where.append("event_type = ?")
                params.append(event_type.strip())
            clause = " AND ".join(where)
            row = conn.execute(
                f"SELECT 1 AS ok FROM program_events WHERE {clause} LIMIT 1",
                tuple(params),
            ).fetchone()
        return row is not None

    def add_approval(
        self,
        *,
        program_id: str,
        gate: str,
        decision: str,
        signer: str,
        signature: str,
        rationale: str | None,
        metadata: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if self.get_program(program_id) is None:
            raise KeyError(program_id)

        now = _utc_now_iso()
        approval_id = str(uuid.uuid4())
        with self._lock, closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO program_approvals(
                    approval_id, program_id, gate, decision, signer, signature,
                    rationale, metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    approval_id,
                    program_id,
                    gate.strip(),
                    decision.strip(),
                    signer.strip(),
                    signature.strip(),
                    _normalize_text(rationale),
                    json.dumps(metadata or {}, ensure_ascii=True),
                    now,
                ),
            )
            conn.execute(
                "UPDATE programs SET updated_at = ? WHERE program_id = ?",
                (now, program_id),
            )
            conn.commit()
        approval = self.get_approval(approval_id)
        if approval is None:
            raise RuntimeError("Failed to create approval")
        return approval

    def get_approval(self, approval_id: str) -> dict[str, Any] | None:
        with self._lock, closing(self._connect()) as conn:
            row = conn.execute(
                """
                SELECT approval_id, program_id, gate, decision, signer, signature,
                       rationale, metadata_json, created_at
                FROM program_approvals
                WHERE approval_id = ?
                """,
                (approval_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_approval(row)

    def list_approvals(self, *, program_id: str, limit: int = 200) -> list[dict[str, Any]]:
        safe_limit = min(max(int(limit), 1), 2000)
        with self._lock, closing(self._connect()) as conn:
            rows = conn.execute(
                """
                SELECT approval_id, program_id, gate, decision, signer, signature,
                       rationale, metadata_json, created_at
                FROM program_approvals
                WHERE program_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (program_id, safe_limit),
            ).fetchall()
        return [self._row_to_approval(row) for row in rows]

    def counts(self) -> dict[str, int]:
        with self._lock, closing(self._connect()) as conn:
            program_count = conn.execute(
                "SELECT COUNT(*) AS c FROM programs"
            ).fetchone()
            event_count = conn.execute(
                "SELECT COUNT(*) AS c FROM program_events"
            ).fetchone()
            approval_count = conn.execute(
                "SELECT COUNT(*) AS c FROM program_approvals"
            ).fetchone()
        return {
            "programs": int(program_count["c"]) if program_count is not None else 0,
            "events": int(event_count["c"]) if event_count is not None else 0,
            "approvals": int(approval_count["c"]) if approval_count is not None else 0,
        }

    @staticmethod
    def _row_to_program(row: sqlite3.Row) -> dict[str, Any]:
        metadata_json = row["metadata_json"]
        metadata = json.loads(metadata_json) if isinstance(metadata_json, str) else {}
        return {
            "program_id": row["program_id"],
            "name": row["name"],
            "indication": row["indication"],
            "target": row["target"],
            "stage": row["stage"],
            "owner": row["owner"],
            "metadata": metadata if isinstance(metadata, dict) else {},
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    @staticmethod
    def _row_to_event(row: sqlite3.Row) -> dict[str, Any]:
        payload_json = row["payload_json"]
        payload = json.loads(payload_json) if isinstance(payload_json, str) else {}
        return {
            "event_id": row["event_id"],
            "program_id": row["program_id"],
            "event_type": row["event_type"],
            "title": row["title"],
            "status": row["status"],
            "source": row["source"],
            "run_id": row["run_id"],
            "payload": payload if isinstance(payload, dict) else {},
            "created_at": row["created_at"],
        }

    @staticmethod
    def _row_to_approval(row: sqlite3.Row) -> dict[str, Any]:
        metadata_json = row["metadata_json"]
        metadata = json.loads(metadata_json) if isinstance(metadata_json, str) else {}
        return {
            "approval_id": row["approval_id"],
            "program_id": row["program_id"],
            "gate": row["gate"],
            "decision": row["decision"],
            "signer": row["signer"],
            "signature": row["signature"],
            "rationale": row["rationale"],
            "metadata": metadata if isinstance(metadata, dict) else {},
            "created_at": row["created_at"],
        }


def _normalize_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
