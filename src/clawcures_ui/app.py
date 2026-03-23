from __future__ import annotations

import json
import traceback
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from clawcures_ui.bridge import CampaignBridge
from clawcures_ui.config import StudioConfig
from clawcures_ui.continuous_agent import ContinuousDiscoveryService
from clawcures_ui.runner import BackgroundRunner
from clawcures_ui.storage import JobStore

_FINISHED_STATUSES: tuple[str, ...] = ("completed", "failed", "cancelled")
_ALLOWED_JOB_STATUSES: frozenset[str] = frozenset(
    {"queued", "running", "completed", "failed", "cancelled"}
)
_ALLOWED_STRUCTURE_SUFFIXES: frozenset[str] = frozenset(
    {".bcif", ".cif", ".mmcif", ".pdb"}
)
_ROLE_VIEWER = "viewer"
_ROLE_OPERATOR = "operator"
_ROLE_ADMIN = "admin"


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
        self.discovery_service: ContinuousDiscoveryService | None = None
        if config.autostart_agent:
            self.discovery_service = ContinuousDiscoveryService(
                self.store,
                self.bridge,
                objective=self.bridge.default_objective(),
            )
            self.discovery_service.start()

    def shutdown(self) -> None:
        if self.discovery_service is not None:
            self.discovery_service.shutdown()
        self.runner.shutdown()
        self.bridge.shutdown()

    def health(self) -> dict[str, Any]:
        tools, warnings = self.bridge.available_tools()
        return {
            "ok": True,
            "tools_count": len(tools),
            "warnings": warnings,
            "job_counts": self.store.status_counts(),
        }

    def examples_payload(self) -> dict[str, Any]:
        return self.bridge.examples()

    def ecosystem_payload(self) -> dict[str, Any]:
        return self.bridge.ecosystem()

    def list_jobs(self, *, query: dict[str, list[str]]) -> dict[str, Any]:
        limit = _parse_limit_query(query, default=100)
        statuses = _parse_statuses_query(query)
        return {
            "jobs": self.store.list_jobs(limit=limit, statuses=statuses),
            "counts": self.store.status_counts(),
        }

    def list_promising_drugs(self, *, query: dict[str, list[str]]) -> dict[str, Any]:
        limit = _parse_limit_query(query, default=300)
        return self.store.list_promising_drugs(limit=limit)

    def read_structure_file(self, *, path_value: str) -> tuple[bytes, str]:
        raw_path = path_value.strip()
        if not raw_path:
            raise BadRequestError("path is required")

        requested = Path(raw_path)
        if requested.is_absolute():
            resolved = requested.resolve()
        else:
            resolved = (self.config.resolved_workspace_root / requested).resolve()

        allowed_roots = (
            self.config.resolved_workspace_root,
            self.config.data_dir.resolve(),
        )
        if not any(_is_within_root(resolved, root) for root in allowed_roots):
            raise NotFoundError("Requested structure path is outside allowed roots")
        if not resolved.exists() or not resolved.is_file():
            raise NotFoundError(f"Structure file not found: {resolved}")
        if resolved.suffix.lower() not in _ALLOWED_STRUCTURE_SUFFIXES:
            raise BadRequestError(
                "Unsupported structure format. Expected one of: .bcif, .cif, .mmcif, .pdb"
            )

        try:
            data = resolved.read_bytes()
        except OSError as exc:
            raise ApiError(f"Failed reading structure file: {exc}") from exc
        return data, _structure_content_type(resolved)

    def get_job(self, job_id: str) -> dict[str, Any]:
        job = self.store.get_job(job_id)
        if job is None:
            raise NotFoundError(f"Unknown job_id: {job_id}")
        return job

    def cancel_job(self, job_id: str) -> dict[str, Any]:
        if self.discovery_service is not None and self.discovery_service.manages_job(
            job_id
        ):
            return self.discovery_service.cancel(job_id)
        try:
            return self.runner.cancel(job_id)
        except KeyError as exc:
            raise NotFoundError(f"Unknown job_id: {job_id}") from exc

    def clear_jobs(self, payload: dict[str, Any]) -> dict[str, Any]:
        statuses = payload.get("statuses")
        if statuses is None:
            target_statuses = _FINISHED_STATUSES
        else:
            if not isinstance(statuses, list) or any(
                not isinstance(item, str) for item in statuses
            ):
                raise BadRequestError("statuses must be an array of strings")
            normalized = tuple(item.strip() for item in statuses if item.strip())
            if not normalized:
                raise BadRequestError("statuses must not be empty")
            invalid = [
                status for status in normalized if status not in _ALLOWED_JOB_STATUSES
            ]
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
        system_prompt = _optional_nonempty_string(
            payload.get("system_prompt"), "system_prompt"
        )
        return self.bridge.plan(objective=objective, system_prompt=system_prompt)

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        objective = _require_nonempty_string(payload.get("objective"), "objective")
        system_prompt = _optional_nonempty_string(
            payload.get("system_prompt"), "system_prompt"
        )
        dry_run = bool(payload.get("dry_run", False))
        autonomous = bool(payload.get("autonomous", False))
        max_rounds = _coerce_int(payload.get("max_rounds", 3), "max_rounds", minimum=1)
        max_calls = _coerce_int(payload.get("max_calls", 10), "max_calls", minimum=1)
        allow_skip_validate_first = bool(
            payload.get("allow_skip_validate_first", False)
        )
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
        bridge_request = dict(request_payload)

        if async_mode:
            job = self.runner.submit(
                kind="campaign_run",
                request=request_payload,
                fn=lambda: self.bridge.run(**bridge_request),
            )
            return {"job": job}

        result = self.bridge.run(**bridge_request)
        return {"result": result}

    def execute_plan(self, payload: dict[str, Any]) -> dict[str, Any]:
        plan = payload.get("plan")
        if not isinstance(plan, dict):
            raise BadRequestError("plan must be a JSON object")
        async_mode = bool(payload.get("async_mode", True))

        if async_mode:
            job = self.runner.submit(
                kind="plan_execute",
                request={"plan": plan},
                fn=lambda: self.bridge.execute_plan(plan=plan),
            )
            return {"job": job}

        result = self.bridge.execute_plan(plan=plan)
        return {"result": result}

    def validate_plan(self, payload: dict[str, Any]) -> dict[str, Any]:
        plan = payload.get("plan")
        if not isinstance(plan, dict):
            raise BadRequestError("plan must be a JSON object")

        max_calls = _coerce_int(payload.get("max_calls", 10), "max_calls", minimum=1)
        allow_skip_validate_first = bool(
            payload.get("allow_skip_validate_first", False)
        )
        return self.bridge.validate_plan(
            plan=plan,
            max_calls=max_calls,
            allow_skip_validate_first=allow_skip_validate_first,
        )


def _parse_statuses_query(query: dict[str, list[str]]) -> tuple[str, ...] | None:
    if "status" not in query:
        return None

    status_items: list[str] = []
    for raw in query.get("status", []):
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


def _parse_limit_query(
    query: dict[str, list[str]],
    *,
    default: int,
) -> int:
    limit = default
    if "limit" not in query:
        return limit
    try:
        return int(query["limit"][0])
    except (TypeError, ValueError, IndexError) as exc:
        raise BadRequestError("Query parameter 'limit' must be an integer") from exc


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


def _json_response(
    handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]
) -> None:
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


def _is_within_root(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _structure_content_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".bcif":
        return "application/octet-stream"
    if suffix == ".pdb":
        return "chemical/x-pdb; charset=utf-8"
    return "chemical/x-cif; charset=utf-8"


def _required_api_role(*, method: str, path: str) -> str | None:
    if not path.startswith("/api/"):
        return None
    normalized_method = method.upper()
    if normalized_method == "GET":
        return _ROLE_VIEWER
    if normalized_method != "POST":
        return _ROLE_VIEWER
    if path == "/api/jobs/clear":
        return _ROLE_ADMIN
    return _ROLE_OPERATOR


def _extract_bearer_token(handler: BaseHTTPRequestHandler) -> str | None:
    raw = str(handler.headers.get("Authorization", "")).strip()
    if not raw:
        return None
    parts = raw.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    token = parts[1].strip()
    return token or None


def _is_role_allowed(*, token_roles: frozenset[str], required_role: str) -> bool:
    if _ROLE_ADMIN in token_roles:
        return True
    if required_role == _ROLE_VIEWER:
        return bool(token_roles)
    if required_role == _ROLE_OPERATOR:
        return _ROLE_OPERATOR in token_roles
    if required_role == _ROLE_ADMIN:
        return _ROLE_ADMIN in token_roles
    return False


def _authorize_request(
    handler: BaseHTTPRequestHandler,
    app: StudioApp,
    *,
    method: str,
    path: str,
) -> tuple[int, dict[str, Any]] | None:
    required_role = _required_api_role(method=method, path=path)
    if required_role is None or not app.config.auth_enabled:
        return None

    token = _extract_bearer_token(handler)
    if token is None:
        return (
            HTTPStatus.UNAUTHORIZED,
            {"error": "Missing bearer token.", "required_role": required_role},
        )

    token_roles = app.config.roles_for_token(token)
    if not token_roles:
        return (
            HTTPStatus.UNAUTHORIZED,
            {"error": "Invalid bearer token.", "required_role": required_role},
        )

    if not _is_role_allowed(token_roles=token_roles, required_role=required_role):
        return (
            HTTPStatus.FORBIDDEN,
            {
                "error": "Insufficient role for endpoint.",
                "required_role": required_role,
                "token_roles": sorted(token_roles),
            },
        )
    return None


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
            return

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path

            try:
                auth_failure = _authorize_request(self, app, method="GET", path=path)
                if auth_failure is not None:
                    status, payload = auth_failure
                    _json_response(self, status, payload)
                    return

                if path == "/api/health":
                    _json_response(self, HTTPStatus.OK, app.health())
                    return
                if path == "/api/examples":
                    _json_response(self, HTTPStatus.OK, app.examples_payload())
                    return
                if path == "/api/ecosystem":
                    _json_response(self, HTTPStatus.OK, app.ecosystem_payload())
                    return
                if path == "/api/jobs":
                    query = parse_qs(parsed.query, keep_blank_values=False)
                    _json_response(self, HTTPStatus.OK, app.list_jobs(query=query))
                    return
                if path == "/api/promising-drugs":
                    query = parse_qs(parsed.query, keep_blank_values=False)
                    _json_response(
                        self, HTTPStatus.OK, app.list_promising_drugs(query=query)
                    )
                    return
                if path == "/structures/file":
                    query = parse_qs(parsed.query, keep_blank_values=False)
                    path_value = query.get("path", [""])[0]
                    data, content_type = app.read_structure_file(
                        path_value=path_value
                    )
                    _text_response(
                        self,
                        status=HTTPStatus.OK,
                        content_type=content_type,
                        data=data,
                    )
                    return
                if path.startswith("/api/jobs/"):
                    job_id = path.removeprefix("/api/jobs/")
                    _json_response(self, HTTPStatus.OK, app.get_job(job_id))
                    return
                if path.startswith("/api/"):
                    _json_response(
                        self, HTTPStatus.NOT_FOUND, {"error": "unknown endpoint"}
                    )
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
                    {"error": str(exc), "type": type(exc).__name__},
                )

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path
            try:
                auth_failure = _authorize_request(self, app, method="POST", path=path)
                if auth_failure is not None:
                    status, payload = auth_failure
                    _json_response(self, status, payload)
                    return

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
                if path == "/api/jobs/clear":
                    _json_response(self, HTTPStatus.OK, app.clear_jobs(payload))
                    return
                if path.startswith("/api/jobs/") and path.endswith("/cancel"):
                    job_id = (
                        path.removeprefix("/api/jobs/")
                        .removesuffix("/cancel")
                        .strip("/")
                    )
                    if not job_id:
                        raise BadRequestError("job_id is required")
                    _json_response(self, HTTPStatus.OK, app.cancel_job(job_id))
                    return
                if path.startswith("/api/"):
                    _json_response(
                        self, HTTPStatus.NOT_FOUND, {"error": "unknown endpoint"}
                    )
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
