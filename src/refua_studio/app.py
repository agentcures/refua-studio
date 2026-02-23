from __future__ import annotations

import json
import traceback
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from refua_studio.bridge import CampaignBridge
from refua_studio.config import StudioConfig
from refua_studio.drug_portfolio import build_drug_portfolio
from refua_studio.runner import BackgroundRunner
from refua_studio.storage import JobStore

_FINISHED_STATUSES: tuple[str, ...] = ("completed", "failed", "cancelled")
_ALLOWED_JOB_STATUSES: frozenset[str] = frozenset(
    {"queued", "running", "completed", "failed", "cancelled"}
)


class ApiError(Exception):
    """API error with explicit HTTP status code."""

    status_code: int = HTTPStatus.INTERNAL_SERVER_ERROR

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class BadRequestError(ApiError):
    """Raised for invalid client payloads."""

    status_code = HTTPStatus.BAD_REQUEST


class NotFoundError(ApiError):
    """Raised when a requested resource does not exist."""

    status_code = HTTPStatus.NOT_FOUND


class StudioApp:
    """Application service container and API implementation."""

    def __init__(self, config: StudioConfig) -> None:
        self.config = config
        self.config.data_dir.mkdir(parents=True, exist_ok=True)
        self.store = JobStore(config.database_path)
        self.runner = BackgroundRunner(self.store, max_workers=config.max_workers)
        self.bridge = CampaignBridge(config.resolved_workspace_root)

    def shutdown(self) -> None:
        self.runner.shutdown()

    def health(self) -> dict[str, Any]:
        tools, warnings = self.bridge.available_tools()
        return {
            "ok": True,
            "tools_count": len(tools),
            "warnings": warnings,
            "job_counts": self.store.status_counts(),
        }

    def config_payload(self) -> dict[str, Any]:
        runtime = self.bridge.runtime_config()
        return {
            "server": {
                "host": self.config.host,
                "port": self.config.port,
                "data_dir": str(self.config.data_dir),
                "workspace_root": str(self.config.resolved_workspace_root),
                "max_workers": self.config.max_workers,
            },
            "runtime": runtime,
        }

    def tools_payload(self) -> dict[str, Any]:
        tools, warnings = self.bridge.available_tools()
        return {
            "tools": tools,
            "warnings": warnings,
        }

    def examples_payload(self) -> dict[str, Any]:
        return self.bridge.examples()

    def ecosystem_payload(self) -> dict[str, Any]:
        return self.bridge.ecosystem()

    def list_jobs(self, *, query: dict[str, list[str]]) -> dict[str, Any]:
        limit = 100
        if "limit" in query:
            try:
                limit = int(query["limit"][0])
            except (TypeError, ValueError, IndexError) as exc:
                raise BadRequestError("Query parameter 'limit' must be an integer") from exc

        statuses = _parse_statuses_query(query)

        return {
            "jobs": self.store.list_jobs(limit=limit, statuses=statuses),
            "counts": self.store.status_counts(),
        }

    def get_job(self, job_id: str) -> dict[str, Any]:
        job = self.store.get_job(job_id)
        if job is None:
            raise NotFoundError(f"Unknown job_id: {job_id}")
        return job

    def cancel_job(self, job_id: str) -> dict[str, Any]:
        try:
            result = self.runner.cancel(job_id)
        except KeyError as exc:
            raise NotFoundError(f"Unknown job_id: {job_id}") from exc
        return result

    def clear_jobs(self, payload: dict[str, Any]) -> dict[str, Any]:
        statuses = payload.get("statuses")
        if statuses is None:
            target_statuses = _FINISHED_STATUSES
        else:
            if not isinstance(statuses, list) or any(not isinstance(s, str) for s in statuses):
                raise BadRequestError("statuses must be an array of strings")
            normalized = tuple(s.strip() for s in statuses if s.strip())
            if not normalized:
                raise BadRequestError("statuses must not be empty")
            invalid = [status for status in normalized if status not in _ALLOWED_JOB_STATUSES]
            if invalid:
                raise BadRequestError(
                    f"Unsupported statuses: {', '.join(sorted(set(invalid)))}"
                )
            target_statuses = normalized

        deleted = self.store.clear_jobs(statuses=target_statuses)
        return {
            "deleted": deleted,
            "statuses": list(target_statuses),
            "counts": self.store.status_counts(),
        }

    def plan(self, payload: dict[str, Any]) -> dict[str, Any]:
        objective = _require_nonempty_string(payload.get("objective"), "objective")
        system_prompt = _optional_nonempty_string(payload.get("system_prompt"), "system_prompt")
        return self.bridge.plan(objective=objective, system_prompt=system_prompt)

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        objective = _require_nonempty_string(payload.get("objective"), "objective")
        system_prompt = _optional_nonempty_string(payload.get("system_prompt"), "system_prompt")
        dry_run = bool(payload.get("dry_run", False))
        autonomous = bool(payload.get("autonomous", False))
        max_rounds = _coerce_int(payload.get("max_rounds", 3), "max_rounds", minimum=1)
        max_calls = _coerce_int(payload.get("max_calls", 10), "max_calls", minimum=1)
        allow_skip_validate_first = bool(payload.get("allow_skip_validate_first", False))
        async_mode = bool(payload.get("async_mode", True))

        plan_payload = payload.get("plan")
        if plan_payload is not None and not isinstance(plan_payload, dict):
            raise BadRequestError("plan must be a JSON object when provided")

        request_payload = {
            "objective": objective,
            "system_prompt": system_prompt,
            "dry_run": dry_run,
            "autonomous": autonomous,
            "max_rounds": max_rounds,
            "max_calls": max_calls,
            "allow_skip_validate_first": allow_skip_validate_first,
            "plan": plan_payload,
        }

        if async_mode:
            job = self.runner.submit(
                kind="campaign_run",
                request=request_payload,
                fn=lambda: self.bridge.run(**request_payload),
            )
            return {
                "job": job,
            }

        result = self.bridge.run(**request_payload)
        return {
            "result": result,
        }

    def execute_plan(self, payload: dict[str, Any]) -> dict[str, Any]:
        plan = payload.get("plan")
        if not isinstance(plan, dict):
            raise BadRequestError("plan must be a JSON object")
        async_mode = bool(payload.get("async_mode", True))

        request_payload = {
            "plan": plan,
        }

        if async_mode:
            job = self.runner.submit(
                kind="plan_execute",
                request=request_payload,
                fn=lambda: self.bridge.execute_plan(plan=plan),
            )
            return {
                "job": job,
            }

        result = self.bridge.execute_plan(plan=plan)
        return {
            "result": result,
        }

    def validate_plan(self, payload: dict[str, Any]) -> dict[str, Any]:
        plan = payload.get("plan")
        if not isinstance(plan, dict):
            raise BadRequestError("plan must be a JSON object")

        max_calls = _coerce_int(payload.get("max_calls", 10), "max_calls", minimum=1)
        allow_skip_validate_first = bool(payload.get("allow_skip_validate_first", False))
        return self.bridge.validate_plan(
            plan=plan,
            max_calls=max_calls,
            allow_skip_validate_first=allow_skip_validate_first,
        )

    def rank_portfolio(self, payload: dict[str, Any]) -> dict[str, Any]:
        programs = payload.get("programs")
        if not isinstance(programs, list):
            raise BadRequestError("programs must be a JSON array")
        normalized: list[dict[str, Any]] = []
        for idx, item in enumerate(programs):
            if not isinstance(item, dict):
                raise BadRequestError(f"programs[{idx}] must be a JSON object")
            normalized.append(item)

        weights = payload.get("weights")
        if weights is not None and not isinstance(weights, dict):
            raise BadRequestError("weights must be a JSON object")

        return self.bridge.rank_portfolio(programs=normalized, weights=weights)

    def drug_portfolio(self, *, query: dict[str, list[str]]) -> dict[str, Any]:
        limit = _query_int(query, name="limit", default=80, minimum=1)
        min_score = _query_float(query, name="min_score", default=50.0, minimum=0.0)
        include_raw = _query_bool(query, name="include_raw", default=False)

        jobs = self.store.list_jobs(limit=500, statuses=("completed",))
        return build_drug_portfolio(
            jobs,
            limit=limit,
            min_score=min_score,
            include_raw=include_raw,
        )

    def clawcures_handoff(self, payload: dict[str, Any]) -> dict[str, Any]:
        objective = _optional_nonempty_string(payload.get("objective"), "objective")
        system_prompt = _optional_nonempty_string(payload.get("system_prompt"), "system_prompt")

        plan_payload = payload.get("plan")
        if plan_payload is not None and not isinstance(plan_payload, dict):
            raise BadRequestError("plan must be a JSON object when provided")

        autonomous = bool(payload.get("autonomous", False))
        dry_run = bool(payload.get("dry_run", True))
        max_calls = _coerce_int(payload.get("max_calls", 10), "max_calls", minimum=1)
        allow_skip_validate_first = bool(payload.get("allow_skip_validate_first", False))
        write_file = bool(payload.get("write_file", True))
        artifact_name = _optional_nonempty_string(payload.get("artifact_name"), "artifact_name")

        artifact_dir = self.config.data_dir / "handoffs"
        return self.bridge.build_clawcures_handoff(
            objective=objective,
            plan=plan_payload,
            system_prompt=system_prompt,
            autonomous=autonomous,
            dry_run=dry_run,
            max_calls=max_calls,
            allow_skip_validate_first=allow_skip_validate_first,
            write_file=write_file,
            artifact_dir=artifact_dir,
            artifact_name=artifact_name,
        )


def _parse_statuses_query(query: dict[str, list[str]]) -> tuple[str, ...] | None:
    if "status" not in query:
        return None
    raw_values = query.get("status", [])
    status_items: list[str] = []
    for raw in raw_values:
        for token in raw.split(","):
            normalized = token.strip()
            if normalized:
                status_items.append(normalized)

    if not status_items:
        return None

    invalid = [status for status in status_items if status not in _ALLOWED_JOB_STATUSES]
    if invalid:
        raise BadRequestError(
            f"Unsupported status filter values: {', '.join(sorted(set(invalid)))}"
        )

    deduped: list[str] = []
    seen: set[str] = set()
    for status in status_items:
        if status in seen:
            continue
        seen.add(status)
        deduped.append(status)
    return tuple(deduped)


def _require_nonempty_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise BadRequestError(f"{field_name} must be a string")
    stripped = value.strip()
    if not stripped:
        raise BadRequestError(f"{field_name} must be non-empty")
    return stripped


def _optional_nonempty_string(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise BadRequestError(f"{field_name} must be a string when provided")
    stripped = value.strip()
    return stripped or None


def _coerce_int(value: Any, field_name: str, *, minimum: int = 0) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise BadRequestError(f"{field_name} must be an integer") from exc
    if parsed < minimum:
        raise BadRequestError(f"{field_name} must be >= {minimum}")
    return parsed


def _query_int(
    query: dict[str, list[str]],
    *,
    name: str,
    default: int,
    minimum: int = 0,
) -> int:
    if name not in query:
        return default
    raw_values = query.get(name) or []
    if not raw_values:
        return default
    try:
        parsed = int(raw_values[0])
    except ValueError as exc:
        raise BadRequestError(f"Query parameter '{name}' must be an integer") from exc
    if parsed < minimum:
        raise BadRequestError(f"Query parameter '{name}' must be >= {minimum}")
    return parsed


def _query_float(
    query: dict[str, list[str]],
    *,
    name: str,
    default: float,
    minimum: float = 0.0,
) -> float:
    if name not in query:
        return default
    raw_values = query.get(name) or []
    if not raw_values:
        return default
    try:
        parsed = float(raw_values[0])
    except ValueError as exc:
        raise BadRequestError(f"Query parameter '{name}' must be a number") from exc
    if parsed < minimum:
        raise BadRequestError(f"Query parameter '{name}' must be >= {minimum}")
    return parsed


def _query_bool(
    query: dict[str, list[str]],
    *,
    name: str,
    default: bool,
) -> bool:
    if name not in query:
        return default
    raw_values = query.get(name) or []
    if not raw_values:
        return default
    normalized = raw_values[0].strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise BadRequestError(
        f"Query parameter '{name}' must be one of true/false/1/0/yes/no/on/off"
    )


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=True, indent=2).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)


def _text_response(
    handler: BaseHTTPRequestHandler,
    *,
    status: int,
    content_type: str,
    data: bytes,
) -> None:
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(data)


def _read_json_body(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length_raw = handler.headers.get("Content-Length", "")
    try:
        length = int(length_raw)
    except ValueError as exc:
        raise BadRequestError("Invalid Content-Length header") from exc

    if length <= 0:
        return {}

    raw = handler.rfile.read(length)
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise BadRequestError("Request body must be valid JSON") from exc

    if not isinstance(parsed, dict):
        raise BadRequestError("Request body must be a JSON object")
    return parsed


def _load_static_file(static_dir: Path, request_path: str) -> tuple[bytes, str] | None:
    static_map = {
        "/assets/app.js": ("app.js", "application/javascript; charset=utf-8"),
        "/assets/styles.css": ("styles.css", "text/css; charset=utf-8"),
    }
    info = static_map.get(request_path)
    if info is None:
        return None
    filename, content_type = info
    file_path = static_dir / filename
    if not file_path.exists():
        return None
    return file_path.read_bytes(), content_type


def create_handler(app: StudioApp):
    class StudioHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, _format: str, *_args: Any) -> None:  # noqa: D401
            # Keep server logs quiet unless explicit debugging is needed.
            return

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path

            try:
                if path == "/api/health":
                    _json_response(self, HTTPStatus.OK, app.health())
                    return
                if path == "/api/config":
                    _json_response(self, HTTPStatus.OK, app.config_payload())
                    return
                if path == "/api/tools":
                    _json_response(self, HTTPStatus.OK, app.tools_payload())
                    return
                if path == "/api/examples":
                    _json_response(self, HTTPStatus.OK, app.examples_payload())
                    return
                if path == "/api/ecosystem":
                    _json_response(self, HTTPStatus.OK, app.ecosystem_payload())
                    return
                if path == "/api/drug-portfolio":
                    query = parse_qs(parsed.query, keep_blank_values=False)
                    _json_response(self, HTTPStatus.OK, app.drug_portfolio(query=query))
                    return
                if path == "/api/jobs":
                    query = parse_qs(parsed.query, keep_blank_values=False)
                    _json_response(self, HTTPStatus.OK, app.list_jobs(query=query))
                    return
                if path.startswith("/api/jobs/"):
                    job_id = path.removeprefix("/api/jobs/")
                    _json_response(self, HTTPStatus.OK, app.get_job(job_id))
                    return

                static_payload = _load_static_file(app.config.static_dir, path)
                if static_payload is not None:
                    data, content_type = static_payload
                    _text_response(
                        self,
                        status=HTTPStatus.OK,
                        content_type=content_type,
                        data=data,
                    )
                    return

                # SPA fallback.
                index_path = app.config.static_dir / "index.html"
                if not index_path.exists():
                    _json_response(
                        self,
                        HTTPStatus.NOT_FOUND,
                        {"error": "static index.html not found"},
                    )
                    return
                _text_response(
                    self,
                    status=HTTPStatus.OK,
                    content_type="text/html; charset=utf-8",
                    data=index_path.read_bytes(),
                )
            except ApiError as exc:
                _json_response(self, exc.status_code, {"error": exc.message})
            except Exception as exc:  # noqa: BLE001
                _json_response(
                    self,
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    {
                        "error": str(exc),
                        "type": type(exc).__name__,
                    },
                )

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path
            try:
                payload = _read_json_body(self)

                if path == "/api/plan":
                    _json_response(self, HTTPStatus.OK, app.plan(payload))
                    return
                if path == "/api/run":
                    _json_response(self, HTTPStatus.OK, app.run(payload))
                    return
                if path == "/api/plan/execute":
                    _json_response(self, HTTPStatus.OK, app.execute_plan(payload))
                    return
                if path == "/api/plan/validate":
                    _json_response(self, HTTPStatus.OK, app.validate_plan(payload))
                    return
                if path == "/api/portfolio/rank":
                    _json_response(self, HTTPStatus.OK, app.rank_portfolio(payload))
                    return
                if path == "/api/clawcures/handoff":
                    _json_response(self, HTTPStatus.OK, app.clawcures_handoff(payload))
                    return
                if path == "/api/jobs/clear":
                    _json_response(self, HTTPStatus.OK, app.clear_jobs(payload))
                    return
                if path.startswith("/api/jobs/") and path.endswith("/cancel"):
                    job_id = path.removeprefix("/api/jobs/").removesuffix("/cancel").strip("/")
                    if not job_id:
                        raise BadRequestError("job_id is required")
                    _json_response(self, HTTPStatus.OK, app.cancel_job(job_id))
                    return

                _json_response(self, HTTPStatus.NOT_FOUND, {"error": "unknown endpoint"})
            except ApiError as exc:
                _json_response(self, exc.status_code, {"error": exc.message})
            except Exception as exc:  # noqa: BLE001
                _json_response(
                    self,
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    {
                        "error": str(exc),
                        "type": type(exc).__name__,
                        "traceback": traceback.format_exc(limit=6),
                    },
                )

    return StudioHandler


def create_server(config: StudioConfig) -> tuple[ThreadingHTTPServer, StudioApp]:
    app = StudioApp(config)
    handler = create_handler(app)
    server = ThreadingHTTPServer((config.host, config.port), handler)
    return server, app


def serve(config: StudioConfig) -> None:
    server, app = create_server(config)
    try:
        server.serve_forever(poll_interval=0.3)
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()
        app.shutdown()
