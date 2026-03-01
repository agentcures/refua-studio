from __future__ import annotations

import json
import traceback
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from refua_studio.bridge import CampaignBridge
from refua_studio.config import StudioConfig
from refua_studio.drug_portfolio import build_drug_portfolio
from refua_studio.program_store import ProgramStore
from refua_studio.runner import BackgroundRunner
from refua_studio.storage import JobStore

_FINISHED_STATUSES: tuple[str, ...] = ("completed", "failed", "cancelled")
_ALLOWED_JOB_STATUSES: frozenset[str] = frozenset(
    {"queued", "running", "completed", "failed", "cancelled"}
)
_ALLOWED_APPROVAL_DECISIONS: frozenset[str] = frozenset(
    {"approved", "rejected", "needs_changes"}
)
_ROLE_VIEWER = "viewer"
_ROLE_OPERATOR = "operator"
_ROLE_ADMIN = "admin"
_STAGE_GATE_TEMPLATES: tuple[dict[str, Any], ...] = (
    {
        "id": "hit_to_lead",
        "label": "Hit To Lead",
        "description": "Advance from initial hits to prioritized lead candidates.",
        "criteria": (
            {"metric": "promising_leads", "min": 3.0, "label": "Promising leads"},
            {"metric": "mean_admet_score", "min": 0.65, "label": "Mean ADMET score"},
            {
                "metric": "mean_binding_probability",
                "min": 0.7,
                "label": "Mean binding probability",
            },
        ),
    },
    {
        "id": "lead_optimization",
        "label": "Lead Optimization",
        "description": "Ensure optimized leads satisfy potency and developability targets.",
        "criteria": (
            {"metric": "top_lead_score", "min": 72.0, "label": "Top lead score"},
            {"metric": "mean_admet_score", "min": 0.72, "label": "Mean ADMET score"},
            {
                "metric": "wetlab_success_rate",
                "min": 0.6,
                "label": "Wet-lab success rate",
            },
        ),
    },
    {
        "id": "ind_enabling",
        "label": "IND-Enabling",
        "description": "Confirm readiness for IND-enabling package assembly.",
        "criteria": (
            {
                "metric": "regulatory_checklist_pass_rate",
                "min": 0.95,
                "label": "Checklist pass rate",
            },
            {
                "metric": "safety_margin_index",
                "min": 1.2,
                "label": "Safety margin index",
            },
            {
                "metric": "manufacturability_index",
                "min": 0.7,
                "label": "Manufacturability index",
            },
        ),
    },
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
        self.programs = ProgramStore(config.database_path)
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
            "program_counts": self.programs.counts(),
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
                "auth": {
                    "enabled": self.config.auth_enabled,
                    "viewer_tokens": len(self.config.auth_tokens),
                    "operator_tokens": len(self.config.operator_tokens),
                    "admin_tokens": len(self.config.admin_tokens),
                },
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

    def command_center_capabilities_payload(self) -> dict[str, Any]:
        return self.bridge.command_center_capabilities()

    def list_programs(self, *, query: dict[str, list[str]]) -> dict[str, Any]:
        limit = _query_int(query, name="limit", default=100, minimum=1)
        stage = _query_optional_string(query, name="stage")
        return {
            "programs": self.programs.list_programs(limit=limit, stage=stage),
            "counts": self.programs.counts(),
        }

    def get_program(
        self, program_id: str, *, query: dict[str, list[str]]
    ) -> dict[str, Any]:
        program = self.programs.get_program(program_id)
        if program is None:
            raise NotFoundError(f"Unknown program_id: {program_id}")
        event_limit = _query_int(query, name="event_limit", default=80, minimum=1)
        approval_limit = _query_int(query, name="approval_limit", default=80, minimum=1)
        return {
            "program": program,
            "events": self.programs.list_events(
                program_id=program_id, limit=event_limit
            ),
            "approvals": self.programs.list_approvals(
                program_id=program_id,
                limit=approval_limit,
            ),
        }

    def upsert_program(self, payload: dict[str, Any]) -> dict[str, Any]:
        program_id = _optional_nonempty_string(payload.get("program_id"), "program_id")
        name = _optional_nonempty_string(payload.get("name"), "name")
        indication = _optional_nonempty_string(payload.get("indication"), "indication")
        target = _optional_nonempty_string(payload.get("target"), "target")
        stage = _optional_nonempty_string(payload.get("stage"), "stage")
        owner = _optional_nonempty_string(payload.get("owner"), "owner")
        metadata = _optional_mapping(payload.get("metadata"), "metadata")
        program = self.programs.upsert_program(
            program_id=program_id,
            name=name,
            indication=indication,
            target=target,
            stage=stage,
            owner=owner,
            metadata=metadata,
        )
        return {
            "program": program,
            "counts": self.programs.counts(),
        }

    def list_program_events(
        self,
        program_id: str,
        *,
        query: dict[str, list[str]],
    ) -> dict[str, Any]:
        if self.programs.get_program(program_id) is None:
            raise NotFoundError(f"Unknown program_id: {program_id}")
        limit = _query_int(query, name="limit", default=200, minimum=1)
        return {
            "program_id": program_id,
            "events": self.programs.list_events(program_id=program_id, limit=limit),
        }

    def add_program_event(
        self,
        program_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        event_type = _require_nonempty_string(payload.get("event_type"), "event_type")
        title = _require_nonempty_string(payload.get("title"), "title")
        status = (
            _optional_nonempty_string(payload.get("status"), "status") or "recorded"
        )
        source = _optional_nonempty_string(payload.get("source"), "source")
        run_id = _optional_nonempty_string(payload.get("run_id"), "run_id")
        event_payload = _optional_mapping(payload.get("payload"), "payload")
        try:
            event = self.programs.add_event(
                program_id=program_id,
                event_type=event_type,
                title=title,
                status=status,
                source=source,
                run_id=run_id,
                payload=event_payload,
            )
        except KeyError as exc:
            raise NotFoundError(f"Unknown program_id: {program_id}") from exc
        return {"event": event}

    def list_program_approvals(
        self,
        program_id: str,
        *,
        query: dict[str, list[str]],
    ) -> dict[str, Any]:
        if self.programs.get_program(program_id) is None:
            raise NotFoundError(f"Unknown program_id: {program_id}")
        limit = _query_int(query, name="limit", default=200, minimum=1)
        return {
            "program_id": program_id,
            "approvals": self.programs.list_approvals(
                program_id=program_id, limit=limit
            ),
        }

    def add_program_approval(
        self,
        program_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        gate = _require_nonempty_string(payload.get("gate"), "gate")
        decision = _require_nonempty_string(payload.get("decision"), "decision").lower()
        if decision not in _ALLOWED_APPROVAL_DECISIONS:
            allowed = ", ".join(sorted(_ALLOWED_APPROVAL_DECISIONS))
            raise BadRequestError(f"decision must be one of: {allowed}")
        signer = _require_nonempty_string(payload.get("signer"), "signer")
        signature = _require_nonempty_string(payload.get("signature"), "signature")
        rationale = _optional_nonempty_string(payload.get("rationale"), "rationale")
        metadata = _optional_mapping(payload.get("metadata"), "metadata")
        try:
            approval = self.programs.add_approval(
                program_id=program_id,
                gate=gate,
                decision=decision,
                signer=signer,
                signature=signature,
                rationale=rationale,
                metadata=metadata,
            )
            self.programs.add_event(
                program_id=program_id,
                event_type="approval",
                title=f"Gate {gate} {decision}",
                status=decision,
                source="refua-studio",
                run_id=None,
                payload={
                    "gate": gate,
                    "decision": decision,
                    "signer": signer,
                },
            )
        except KeyError as exc:
            raise NotFoundError(f"Unknown program_id: {program_id}") from exc
        return {"approval": approval}

    def stage_gate_templates(self) -> dict[str, Any]:
        return {
            "templates": [
                self._stage_gate_template_payload(item)
                for item in _STAGE_GATE_TEMPLATES
            ],
            "count": len(_STAGE_GATE_TEMPLATES),
        }

    def evaluate_program_gate(
        self,
        program_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        program = self.programs.get_program(program_id)
        if program is None:
            raise NotFoundError(f"Unknown program_id: {program_id}")

        template_id = _require_nonempty_string(
            payload.get("template_id"), "template_id"
        )
        template = self._stage_gate_template(template_id)

        metrics = payload.get("metrics")
        if not isinstance(metrics, dict):
            raise BadRequestError("metrics must be a JSON object")
        normalized_metrics = {
            str(key): _to_metric_float(value) for key, value in metrics.items()
        }

        checks: list[dict[str, Any]] = []
        passed = True
        for criterion in template["criteria"]:
            metric_name = str(criterion["metric"])
            threshold = float(criterion["min"])
            observed = normalized_metrics.get(metric_name)
            criterion_passed = observed is not None and observed >= threshold
            if not criterion_passed:
                passed = False
            checks.append(
                {
                    "metric": metric_name,
                    "label": str(criterion.get("label", metric_name)),
                    "minimum": threshold,
                    "observed": observed,
                    "passed": criterion_passed,
                }
            )

        recommendation = "approved" if passed else "needs_changes"
        summary = {
            "program_id": program_id,
            "template_id": template["id"],
            "template_label": template["label"],
            "description": template.get("description"),
            "passed": passed,
            "recommendation": recommendation,
            "checks": checks,
            "metrics": normalized_metrics,
        }

        auto_record = bool(payload.get("auto_record", True))
        if auto_record:
            signer = (
                _optional_nonempty_string(payload.get("signer"), "signer")
                or program.get("owner")
                or "refua-studio"
            )
            gate_name = template["id"]
            self.programs.add_approval(
                program_id=program_id,
                gate=gate_name,
                decision=recommendation,
                signer=signer,
                signature=f"studio-gate:{datetime.now(UTC).isoformat()}",
                rationale=(
                    "Automated stage-gate recommendation from template "
                    f"'{template['id']}'"
                ),
                metadata={
                    "checks": checks,
                    "metrics": normalized_metrics,
                },
            )
            self.programs.add_event(
                program_id=program_id,
                event_type="stage_gate",
                title=f"Stage gate {template['label']} -> {recommendation}",
                status=recommendation,
                source="refua-studio",
                run_id=None,
                payload=summary,
            )

        return {"evaluation": summary}

    def sync_program_jobs(self, payload: dict[str, Any]) -> dict[str, Any]:
        statuses = payload.get("statuses")
        selected_statuses: tuple[str, ...] = ("completed", "failed", "cancelled")
        if statuses is not None:
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
            selected_statuses = normalized

        limit = _coerce_int(payload.get("limit", 500), "limit", minimum=1)
        jobs = self.store.list_jobs(limit=limit, statuses=selected_statuses)

        linked = 0
        skipped = 0
        touched_programs: set[str] = set()
        for job in jobs:
            request = job.get("request")
            if not isinstance(request, dict):
                skipped += 1
                continue
            program_id = request.get("program_id")
            if not isinstance(program_id, str) or not program_id.strip():
                skipped += 1
                continue
            program_id = program_id.strip()
            if self.programs.get_program(program_id) is None:
                skipped += 1
                continue

            run_id = str(job.get("job_id") or "")
            status = str(job.get("status") or "")
            if not run_id or not status:
                skipped += 1
                continue

            if self.programs.has_event_for_run(
                program_id=program_id,
                run_id=run_id,
                status=status,
                event_type="job_lifecycle",
            ):
                skipped += 1
                continue

            result = job.get("result")
            payload_preview: dict[str, Any] = {
                "kind": job.get("kind"),
                "status": status,
                "updated_at": job.get("updated_at"),
                "error": job.get("error"),
            }
            if isinstance(result, dict):
                payload_preview["result_keys"] = sorted(result.keys())[:30]
            self.programs.add_event(
                program_id=program_id,
                event_type="job_lifecycle",
                title=f"{job.get('kind')} {status}",
                status=status,
                source="refua-studio",
                run_id=run_id,
                payload=payload_preview,
            )
            linked += 1
            touched_programs.add(program_id)

        return {
            "linked_events": linked,
            "skipped_jobs": skipped,
            "touched_programs": sorted(touched_programs),
            "statuses": list(selected_statuses),
            "jobs_scanned": len(jobs),
        }

    def data_datasets(self, *, query: dict[str, list[str]]) -> dict[str, Any]:
        tag = _query_optional_string(query, name="tag")
        limit = _query_int(query, name="limit", default=120, minimum=1)
        try:
            return self.bridge.list_data_datasets(tag=tag, limit=limit)
        except Exception as exc:  # noqa: BLE001
            raise BadRequestError(str(exc)) from exc

    def data_materialize(self, payload: dict[str, Any]) -> dict[str, Any]:
        dataset_id = _require_nonempty_string(payload.get("dataset_id"), "dataset_id")
        force = bool(payload.get("force", False))
        refresh = bool(payload.get("refresh", False))
        async_mode = bool(payload.get("async_mode", True))
        chunksize = _coerce_int(
            payload.get("chunksize", 100_000), "chunksize", minimum=1
        )
        timeout_seconds = _coerce_float(
            payload.get("timeout_seconds", 120.0),
            "timeout_seconds",
            minimum=0.1,
        )
        request_payload = {
            "dataset_id": dataset_id,
            "force": force,
            "refresh": refresh,
            "chunksize": chunksize,
            "timeout_seconds": timeout_seconds,
        }
        if async_mode:
            job = self.runner.submit(
                kind="data_materialize",
                request=request_payload,
                fn=lambda: self.bridge.materialize_dataset(
                    dataset_id=dataset_id,
                    force=force,
                    refresh=refresh,
                    chunksize=chunksize,
                    timeout_seconds=timeout_seconds,
                ),
            )
            return {"job": job}
        try:
            result = self.bridge.materialize_dataset(
                dataset_id=dataset_id,
                force=force,
                refresh=refresh,
                chunksize=chunksize,
                timeout_seconds=timeout_seconds,
            )
        except Exception as exc:  # noqa: BLE001
            raise BadRequestError(str(exc)) from exc
        return {"result": result}

    def benchmark_gate(self, payload: dict[str, Any]) -> dict[str, Any]:
        suite_path = _require_nonempty_string(payload.get("suite_path"), "suite_path")
        baseline_run_path = _require_nonempty_string(
            payload.get("baseline_run_path"),
            "baseline_run_path",
        )
        adapter_spec = (
            _optional_nonempty_string(payload.get("adapter_spec"), "adapter_spec")
            or "file"
        )
        adapter_config = _optional_mapping(
            payload.get("adapter_config"), "adapter_config"
        )
        async_mode = bool(payload.get("async_mode", True))

        model_name = _optional_nonempty_string(payload.get("model_name"), "model_name")
        model_version = _optional_nonempty_string(
            payload.get("model_version"), "model_version"
        )
        candidate_output_path = _optional_nonempty_string(
            payload.get("candidate_output_path"),
            "candidate_output_path",
        )
        comparison_output_path = _optional_nonempty_string(
            payload.get("comparison_output_path"),
            "comparison_output_path",
        )

        min_effect_size = _coerce_float(
            payload.get("min_effect_size", 0.0),
            "min_effect_size",
            minimum=0.0,
        )
        bootstrap_resamples = _coerce_int(
            payload.get("bootstrap_resamples", 0),
            "bootstrap_resamples",
            minimum=0,
        )
        confidence_level = _coerce_float(
            payload.get("confidence_level", 0.95),
            "confidence_level",
            minimum=0.01,
        )
        bootstrap_seed: int | None = None
        if payload.get("bootstrap_seed") is not None:
            bootstrap_seed = _coerce_int(
                payload.get("bootstrap_seed"), "bootstrap_seed"
            )
        fail_on_uncertain = bool(payload.get("fail_on_uncertain", False))

        request_payload = {
            "suite_path": suite_path,
            "baseline_run_path": baseline_run_path,
            "adapter_spec": adapter_spec,
            "adapter_config": adapter_config,
            "model_name": model_name,
            "model_version": model_version,
            "candidate_output_path": candidate_output_path,
            "comparison_output_path": comparison_output_path,
            "min_effect_size": min_effect_size,
            "bootstrap_resamples": bootstrap_resamples,
            "confidence_level": confidence_level,
            "bootstrap_seed": bootstrap_seed,
            "fail_on_uncertain": fail_on_uncertain,
        }

        if async_mode:
            job = self.runner.submit(
                kind="benchmark_gate",
                request=request_payload,
                fn=lambda: self.bridge.gate_benchmark(
                    suite_path=suite_path,
                    baseline_run_path=baseline_run_path,
                    adapter_spec=adapter_spec,
                    adapter_config=adapter_config,
                    model_name=model_name,
                    model_version=model_version,
                    min_effect_size=min_effect_size,
                    bootstrap_resamples=bootstrap_resamples,
                    confidence_level=confidence_level,
                    bootstrap_seed=bootstrap_seed,
                    fail_on_uncertain=fail_on_uncertain,
                    candidate_output_path=candidate_output_path,
                    comparison_output_path=comparison_output_path,
                ),
            )
            return {"job": job}

        try:
            result = self.bridge.gate_benchmark(
                suite_path=suite_path,
                baseline_run_path=baseline_run_path,
                adapter_spec=adapter_spec,
                adapter_config=adapter_config,
                model_name=model_name,
                model_version=model_version,
                min_effect_size=min_effect_size,
                bootstrap_resamples=bootstrap_resamples,
                confidence_level=confidence_level,
                bootstrap_seed=bootstrap_seed,
                fail_on_uncertain=fail_on_uncertain,
                candidate_output_path=candidate_output_path,
                comparison_output_path=comparison_output_path,
            )
        except Exception as exc:  # noqa: BLE001
            raise BadRequestError(str(exc)) from exc
        return {"result": result}

    def wetlab_providers(self) -> dict[str, Any]:
        return self.bridge.wetlab_providers()

    def wetlab_validate_protocol(self, payload: dict[str, Any]) -> dict[str, Any]:
        protocol = payload.get("protocol") if "protocol" in payload else payload
        if not isinstance(protocol, dict):
            raise BadRequestError("protocol must be a JSON object")
        try:
            return self.bridge.wetlab_validate_protocol(protocol=protocol)
        except Exception as exc:  # noqa: BLE001
            raise BadRequestError(str(exc)) from exc

    def wetlab_compile_protocol(self, payload: dict[str, Any]) -> dict[str, Any]:
        provider = _require_nonempty_string(payload.get("provider"), "provider")
        protocol = payload.get("protocol")
        if not isinstance(protocol, dict):
            raise BadRequestError("protocol must be a JSON object")
        try:
            return self.bridge.wetlab_compile_protocol(
                provider=provider, protocol=protocol
            )
        except Exception as exc:  # noqa: BLE001
            raise BadRequestError(str(exc)) from exc

    def wetlab_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        provider = _require_nonempty_string(payload.get("provider"), "provider")
        protocol = payload.get("protocol")
        if not isinstance(protocol, dict):
            raise BadRequestError("protocol must be a JSON object")
        dry_run = bool(payload.get("dry_run", True))
        async_mode = bool(payload.get("async_mode", True))
        metadata = _optional_mapping(payload.get("metadata"), "metadata") or {}
        program_id = _optional_nonempty_string(payload.get("program_id"), "program_id")
        if program_id and self.programs.get_program(program_id) is None:
            raise NotFoundError(f"Unknown program_id: {program_id}")

        request_payload = {
            "provider": provider,
            "protocol": protocol,
            "dry_run": dry_run,
            "metadata": metadata,
            "program_id": program_id,
        }

        if async_mode:
            job = self.runner.submit(
                kind="wetlab_run",
                request=request_payload,
                fn=lambda: self.bridge.wetlab_run_protocol(
                    provider=provider,
                    protocol=protocol,
                    dry_run=dry_run,
                    metadata=metadata,
                ),
            )
            if program_id:
                try:
                    self.programs.add_event(
                        program_id=program_id,
                        event_type="wetlab_run",
                        title=f"Wet-lab run submitted ({provider})",
                        status="queued",
                        source="refua-studio",
                        run_id=job["job_id"],
                        payload={"dry_run": dry_run},
                    )
                except KeyError as exc:
                    raise NotFoundError(f"Unknown program_id: {program_id}") from exc
            return {"job": job}

        try:
            result = self.bridge.wetlab_run_protocol(
                provider=provider,
                protocol=protocol,
                dry_run=dry_run,
                metadata=metadata,
            )
        except Exception as exc:  # noqa: BLE001
            raise BadRequestError(str(exc)) from exc

        if program_id:
            try:
                self.programs.add_event(
                    program_id=program_id,
                    event_type="wetlab_run",
                    title=f"Wet-lab run completed ({provider})",
                    status="completed",
                    source="refua-studio",
                    run_id=None,
                    payload=result.get("lineage_event"),
                )
            except KeyError as exc:
                raise NotFoundError(f"Unknown program_id: {program_id}") from exc

        return {"result": result}

    def list_regulatory_bundles(self, *, query: dict[str, list[str]]) -> dict[str, Any]:
        limit = _query_int(query, name="limit", default=100, minimum=1)
        root = self.config.data_dir / "regulatory"
        bundles: list[dict[str, Any]] = []
        if root.exists():
            for path in sorted(
                root.glob("*"), key=lambda item: item.name, reverse=True
            ):
                if not path.is_dir():
                    continue
                manifest_path = path / "manifest.json"
                if not manifest_path.exists():
                    continue
                try:
                    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    continue
                if not isinstance(payload, dict):
                    continue
                bundles.append(
                    {
                        "bundle_dir": str(path),
                        "bundle_id": payload.get("bundle_id"),
                        "campaign_run_id": payload.get("campaign_run_id"),
                        "created_at": payload.get("created_at"),
                        "decision_count": payload.get("decision_count"),
                        "checklist_summary": payload.get("checklist_summary", {}),
                    }
                )
                if len(bundles) >= limit:
                    break
        return {"bundles": bundles, "count": len(bundles)}

    def build_regulatory_bundle(self, payload: dict[str, Any]) -> dict[str, Any]:
        job_id = _optional_nonempty_string(payload.get("job_id"), "job_id")
        campaign_run = payload.get("campaign_run")
        if campaign_run is not None and not isinstance(campaign_run, dict):
            raise BadRequestError("campaign_run must be a JSON object when provided")

        if campaign_run is None:
            if job_id is None:
                raise BadRequestError("Either job_id or campaign_run is required")
            job = self.store.get_job(job_id)
            if job is None:
                raise NotFoundError(f"Unknown job_id: {job_id}")
            campaign_run = self._campaign_run_from_job(job)

        output_dir = _optional_nonempty_string(payload.get("output_dir"), "output_dir")
        if output_dir is None:
            stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            output_dir = str(
                (self.config.data_dir / "regulatory" / f"bundle_{stamp}").resolve()
            )

        data_manifest_paths = _optional_string_list(
            payload.get("data_manifest_paths"), "data_manifest_paths"
        )
        extra_artifacts = _optional_string_list(
            payload.get("extra_artifacts"), "extra_artifacts"
        )
        include_checklists = bool(payload.get("include_checklists", True))
        checklist_templates = _optional_string_list(
            payload.get("checklist_templates"), "checklist_templates"
        )
        checklist_strict = bool(payload.get("checklist_strict", False))
        checklist_require_no_manual_review = bool(
            payload.get("checklist_require_no_manual_review", False)
        )
        overwrite = bool(payload.get("overwrite", True))
        async_mode = bool(payload.get("async_mode", True))
        program_id = _optional_nonempty_string(payload.get("program_id"), "program_id")
        if program_id and self.programs.get_program(program_id) is None:
            raise NotFoundError(f"Unknown program_id: {program_id}")

        request_payload = {
            "job_id": job_id,
            "output_dir": output_dir,
            "data_manifest_paths": data_manifest_paths,
            "extra_artifacts": extra_artifacts,
            "include_checklists": include_checklists,
            "checklist_templates": checklist_templates,
            "checklist_strict": checklist_strict,
            "checklist_require_no_manual_review": checklist_require_no_manual_review,
            "overwrite": overwrite,
            "program_id": program_id,
        }

        if async_mode:
            job = self.runner.submit(
                kind="regulatory_bundle_build",
                request=request_payload,
                fn=lambda: self.bridge.build_regulatory_bundle(
                    campaign_run=campaign_run,
                    output_dir=output_dir,
                    data_manifest_paths=data_manifest_paths,
                    extra_artifacts=extra_artifacts,
                    include_checklists=include_checklists,
                    checklist_templates=checklist_templates,
                    checklist_strict=checklist_strict,
                    checklist_require_no_manual_review=checklist_require_no_manual_review,
                    overwrite=overwrite,
                ),
            )
            if program_id:
                try:
                    self.programs.add_event(
                        program_id=program_id,
                        event_type="regulatory_bundle",
                        title="Regulatory bundle build submitted",
                        status="queued",
                        source="refua-studio",
                        run_id=job["job_id"],
                        payload={"output_dir": output_dir},
                    )
                except KeyError as exc:
                    raise NotFoundError(f"Unknown program_id: {program_id}") from exc
            return {"job": job}

        try:
            result = self.bridge.build_regulatory_bundle(
                campaign_run=campaign_run,
                output_dir=output_dir,
                data_manifest_paths=data_manifest_paths,
                extra_artifacts=extra_artifacts,
                include_checklists=include_checklists,
                checklist_templates=checklist_templates,
                checklist_strict=checklist_strict,
                checklist_require_no_manual_review=checklist_require_no_manual_review,
                overwrite=overwrite,
            )
        except Exception as exc:  # noqa: BLE001
            raise BadRequestError(str(exc)) from exc

        if program_id:
            try:
                self.programs.add_event(
                    program_id=program_id,
                    event_type="regulatory_bundle",
                    title="Regulatory bundle built",
                    status="completed",
                    source="refua-studio",
                    run_id=None,
                    payload={"bundle_dir": result.get("bundle_dir")},
                )
            except KeyError as exc:
                raise NotFoundError(f"Unknown program_id: {program_id}") from exc

        return {"result": result}

    def verify_regulatory_bundle(self, payload: dict[str, Any]) -> dict[str, Any]:
        bundle_dir = _require_nonempty_string(payload.get("bundle_dir"), "bundle_dir")
        try:
            result = self.bridge.verify_regulatory_bundle(bundle_dir=bundle_dir)
        except Exception as exc:  # noqa: BLE001
            raise BadRequestError(str(exc)) from exc
        return {"result": result}

    @staticmethod
    def _campaign_run_from_job(job: dict[str, Any]) -> dict[str, Any]:
        request = job.get("request")
        result = job.get("result")
        payload: dict[str, Any] = {}
        if isinstance(request, dict):
            payload.update(request)
        if isinstance(result, dict):
            payload.update(result)
        payload.setdefault("source_job_id", job.get("job_id"))
        payload.setdefault("source_job_kind", job.get("kind"))
        payload.setdefault("source_job_status", job.get("status"))
        return payload

    @staticmethod
    def _stage_gate_template(template_id: str) -> dict[str, Any]:
        for template in _STAGE_GATE_TEMPLATES:
            if str(template.get("id")) == template_id:
                return template
        available = ", ".join(sorted(str(item["id"]) for item in _STAGE_GATE_TEMPLATES))
        raise BadRequestError(
            f"Unknown template_id '{template_id}'. Available: {available}"
        )

    @staticmethod
    def _stage_gate_template_payload(template: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": template["id"],
            "label": template["label"],
            "description": template.get("description"),
            "criteria": [
                {
                    "metric": str(item["metric"]),
                    "label": str(item.get("label", item["metric"])),
                    "minimum": float(item["min"]),
                }
                for item in template["criteria"]
            ],
        }

    def list_jobs(self, *, query: dict[str, list[str]]) -> dict[str, Any]:
        limit = 100
        if "limit" in query:
            try:
                limit = int(query["limit"][0])
            except (TypeError, ValueError, IndexError) as exc:
                raise BadRequestError(
                    "Query parameter 'limit' must be an integer"
                ) from exc

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
            if not isinstance(statuses, list) or any(
                not isinstance(s, str) for s in statuses
            ):
                raise BadRequestError("statuses must be an array of strings")
            normalized = tuple(s.strip() for s in statuses if s.strip())
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
        program_id = _optional_nonempty_string(payload.get("program_id"), "program_id")
        if program_id and self.programs.get_program(program_id) is None:
            raise NotFoundError(f"Unknown program_id: {program_id}")

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
            "program_id": program_id,
        }
        bridge_request = {
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
                fn=lambda: self.bridge.run(**bridge_request),
            )
            if program_id:
                try:
                    self.programs.add_event(
                        program_id=program_id,
                        event_type="campaign_run",
                        title="Campaign run submitted",
                        status="queued",
                        source="refua-studio",
                        run_id=job["job_id"],
                        payload={"objective": objective, "autonomous": autonomous},
                    )
                except KeyError as exc:
                    raise NotFoundError(f"Unknown program_id: {program_id}") from exc
            return {
                "job": job,
            }

        result = self.bridge.run(**bridge_request)
        if program_id:
            try:
                self.programs.add_event(
                    program_id=program_id,
                    event_type="campaign_run",
                    title="Campaign run completed",
                    status="completed",
                    source="refua-studio",
                    run_id=None,
                    payload={"objective": objective, "autonomous": autonomous},
                )
            except KeyError as exc:
                raise NotFoundError(f"Unknown program_id: {program_id}") from exc
        return {
            "result": result,
        }

    def execute_plan(self, payload: dict[str, Any]) -> dict[str, Any]:
        plan = payload.get("plan")
        if not isinstance(plan, dict):
            raise BadRequestError("plan must be a JSON object")
        async_mode = bool(payload.get("async_mode", True))
        program_id = _optional_nonempty_string(payload.get("program_id"), "program_id")
        if program_id and self.programs.get_program(program_id) is None:
            raise NotFoundError(f"Unknown program_id: {program_id}")

        request_payload = {
            "plan": plan,
            "program_id": program_id,
        }

        if async_mode:
            job = self.runner.submit(
                kind="plan_execute",
                request=request_payload,
                fn=lambda: self.bridge.execute_plan(plan=plan),
            )
            if program_id:
                try:
                    self.programs.add_event(
                        program_id=program_id,
                        event_type="plan_execute",
                        title="Plan execution submitted",
                        status="queued",
                        source="refua-studio",
                        run_id=job["job_id"],
                        payload={"calls": len(plan.get("calls", []))},
                    )
                except KeyError as exc:
                    raise NotFoundError(f"Unknown program_id: {program_id}") from exc
            return {
                "job": job,
            }

        result = self.bridge.execute_plan(plan=plan)
        if program_id:
            try:
                self.programs.add_event(
                    program_id=program_id,
                    event_type="plan_execute",
                    title="Plan execution completed",
                    status="completed",
                    source="refua-studio",
                    run_id=None,
                    payload={"calls": len(plan.get("calls", []))},
                )
            except KeyError as exc:
                raise NotFoundError(f"Unknown program_id: {program_id}") from exc
        return {
            "result": result,
        }

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

    def promising_cures(self, *, query: dict[str, list[str]]) -> dict[str, Any]:
        return self.drug_portfolio(query=query)

    def clawcures_handoff(self, payload: dict[str, Any]) -> dict[str, Any]:
        objective = _optional_nonempty_string(payload.get("objective"), "objective")
        system_prompt = _optional_nonempty_string(
            payload.get("system_prompt"), "system_prompt"
        )

        plan_payload = payload.get("plan")
        if plan_payload is not None and not isinstance(plan_payload, dict):
            raise BadRequestError("plan must be a JSON object when provided")

        autonomous = bool(payload.get("autonomous", False))
        dry_run = bool(payload.get("dry_run", True))
        max_calls = _coerce_int(payload.get("max_calls", 10), "max_calls", minimum=1)
        allow_skip_validate_first = bool(
            payload.get("allow_skip_validate_first", False)
        )
        write_file = bool(payload.get("write_file", True))
        artifact_name = _optional_nonempty_string(
            payload.get("artifact_name"), "artifact_name"
        )

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

    def clinical_trials(self) -> dict[str, Any]:
        return self.bridge.list_clinical_trials()

    def clinical_trial(self, trial_id: str) -> dict[str, Any]:
        try:
            return self.bridge.get_clinical_trial(trial_id=trial_id)
        except KeyError as exc:
            raise NotFoundError(f"Unknown trial_id: {trial_id}") from exc

    def add_clinical_trial(self, payload: dict[str, Any]) -> dict[str, Any]:
        trial_id = _optional_nonempty_string(payload.get("trial_id"), "trial_id")
        indication = _optional_nonempty_string(payload.get("indication"), "indication")
        phase = _optional_nonempty_string(payload.get("phase"), "phase")
        objective = _optional_nonempty_string(payload.get("objective"), "objective")
        status = _optional_nonempty_string(payload.get("status"), "status")
        config = _optional_mapping(payload.get("config"), "config")
        metadata = _optional_mapping(payload.get("metadata"), "metadata")

        try:
            return self.bridge.add_clinical_trial(
                trial_id=trial_id,
                config=config,
                indication=indication,
                phase=phase,
                objective=objective,
                status=status,
                metadata=metadata,
            )
        except ValueError as exc:
            raise BadRequestError(str(exc)) from exc

    def update_clinical_trial(self, payload: dict[str, Any]) -> dict[str, Any]:
        trial_id = _require_nonempty_string(payload.get("trial_id"), "trial_id")
        updates = payload.get("updates")
        if not isinstance(updates, dict):
            raise BadRequestError("updates must be a JSON object")

        try:
            return self.bridge.update_clinical_trial(trial_id=trial_id, updates=updates)
        except KeyError as exc:
            raise NotFoundError(f"Unknown trial_id: {trial_id}") from exc
        except ValueError as exc:
            raise BadRequestError(str(exc)) from exc

    def remove_clinical_trial(self, payload: dict[str, Any]) -> dict[str, Any]:
        trial_id = _require_nonempty_string(payload.get("trial_id"), "trial_id")
        try:
            return self.bridge.remove_clinical_trial(trial_id=trial_id)
        except ValueError as exc:
            raise BadRequestError(str(exc)) from exc

    def enroll_clinical_patient(self, payload: dict[str, Any]) -> dict[str, Any]:
        trial_id = _require_nonempty_string(payload.get("trial_id"), "trial_id")
        patient_id = _optional_nonempty_string(payload.get("patient_id"), "patient_id")
        source = _optional_nonempty_string(payload.get("source"), "source")
        arm_id = _optional_nonempty_string(payload.get("arm_id"), "arm_id")
        site_id = _optional_nonempty_string(payload.get("site_id"), "site_id")
        demographics = _optional_mapping(payload.get("demographics"), "demographics")
        baseline = _optional_mapping(payload.get("baseline"), "baseline")
        metadata = _optional_mapping(payload.get("metadata"), "metadata")

        try:
            return self.bridge.enroll_clinical_patient(
                trial_id=trial_id,
                patient_id=patient_id,
                source=source,
                arm_id=arm_id,
                site_id=site_id,
                demographics=demographics,
                baseline=baseline,
                metadata=metadata,
            )
        except KeyError as exc:
            raise NotFoundError(f"Unknown trial_id: {trial_id}") from exc
        except ValueError as exc:
            raise BadRequestError(str(exc)) from exc

    def enroll_simulated_clinical_patients(
        self, payload: dict[str, Any]
    ) -> dict[str, Any]:
        trial_id = _require_nonempty_string(payload.get("trial_id"), "trial_id")
        count = _coerce_int(payload.get("count", 0), "count", minimum=1)

        seed_raw = payload.get("seed")
        seed: int | None = None
        if seed_raw is not None:
            seed = _coerce_int(seed_raw, "seed")

        try:
            return self.bridge.enroll_simulated_clinical_patients(
                trial_id=trial_id,
                count=count,
                seed=seed,
            )
        except KeyError as exc:
            raise NotFoundError(f"Unknown trial_id: {trial_id}") from exc
        except ValueError as exc:
            raise BadRequestError(str(exc)) from exc

    def add_clinical_result(self, payload: dict[str, Any]) -> dict[str, Any]:
        trial_id = _require_nonempty_string(payload.get("trial_id"), "trial_id")
        patient_id = _require_nonempty_string(payload.get("patient_id"), "patient_id")
        values = payload.get("values")
        if not isinstance(values, dict):
            raise BadRequestError("values must be a JSON object")
        result_type = (
            _optional_nonempty_string(payload.get("result_type"), "result_type")
            or "endpoint"
        )
        visit = _optional_nonempty_string(payload.get("visit"), "visit")
        source = _optional_nonempty_string(payload.get("source"), "source")
        site_id = _optional_nonempty_string(payload.get("site_id"), "site_id")

        try:
            return self.bridge.add_clinical_result(
                trial_id=trial_id,
                patient_id=patient_id,
                values=values,
                result_type=result_type,
                visit=visit,
                source=source,
                site_id=site_id,
            )
        except KeyError as exc:
            raise NotFoundError(f"Unknown trial_id: {trial_id}") from exc
        except ValueError as exc:
            raise BadRequestError(str(exc)) from exc

    def simulate_clinical_trial(self, payload: dict[str, Any]) -> dict[str, Any]:
        trial_id = _require_nonempty_string(payload.get("trial_id"), "trial_id")
        async_mode = bool(payload.get("async_mode", True))

        replicates_raw = payload.get("replicates")
        replicates: int | None = None
        if replicates_raw is not None:
            replicates = _coerce_int(replicates_raw, "replicates", minimum=1)

        seed_raw = payload.get("seed")
        seed: int | None = None
        if seed_raw is not None:
            seed = _coerce_int(seed_raw, "seed")

        request_payload = {
            "trial_id": trial_id,
            "replicates": replicates,
            "seed": seed,
        }

        if async_mode:
            job = self.runner.submit(
                kind="clinical_trial_simulation",
                request=request_payload,
                fn=lambda: self.bridge.simulate_clinical_trial(
                    trial_id=trial_id,
                    replicates=replicates,
                    seed=seed,
                ),
            )
            return {
                "job": job,
            }

        try:
            result = self.bridge.simulate_clinical_trial(
                trial_id=trial_id,
                replicates=replicates,
                seed=seed,
            )
        except KeyError as exc:
            raise NotFoundError(f"Unknown trial_id: {trial_id}") from exc
        except ValueError as exc:
            raise BadRequestError(str(exc)) from exc

        return {
            "result": result,
        }

    def clinical_trial_sites(self, trial_id: str) -> dict[str, Any]:
        try:
            return self.bridge.list_clinical_sites(trial_id=trial_id)
        except KeyError as exc:
            raise NotFoundError(f"Unknown trial_id: {trial_id}") from exc

    def clinical_trial_ops(self, trial_id: str) -> dict[str, Any]:
        try:
            return self.bridge.clinical_ops_snapshot(trial_id=trial_id)
        except KeyError as exc:
            raise NotFoundError(f"Unknown trial_id: {trial_id}") from exc

    def upsert_clinical_site(self, payload: dict[str, Any]) -> dict[str, Any]:
        trial_id = _require_nonempty_string(payload.get("trial_id"), "trial_id")
        site_id = _require_nonempty_string(payload.get("site_id"), "site_id")
        name = _optional_nonempty_string(payload.get("name"), "name")
        country_id = _optional_nonempty_string(payload.get("country_id"), "country_id")
        status = _optional_nonempty_string(payload.get("status"), "status")
        principal_investigator = _optional_nonempty_string(
            payload.get("principal_investigator"),
            "principal_investigator",
        )
        metadata = _optional_mapping(payload.get("metadata"), "metadata")
        target_raw = payload.get("target_enrollment")
        target_enrollment: int | None = None
        if target_raw is not None:
            target_enrollment = _coerce_int(
                target_raw,
                "target_enrollment",
                minimum=0,
            )

        try:
            return self.bridge.upsert_clinical_site(
                trial_id=trial_id,
                site_id=site_id,
                name=name,
                country_id=country_id,
                status=status,
                principal_investigator=principal_investigator,
                target_enrollment=target_enrollment,
                metadata=metadata,
            )
        except KeyError as exc:
            raise NotFoundError(f"Unknown trial_id: {trial_id}") from exc
        except ValueError as exc:
            raise BadRequestError(str(exc)) from exc

    def add_clinical_screening(self, payload: dict[str, Any]) -> dict[str, Any]:
        trial_id = _require_nonempty_string(payload.get("trial_id"), "trial_id")
        site_id = _require_nonempty_string(payload.get("site_id"), "site_id")
        patient_id = _optional_nonempty_string(payload.get("patient_id"), "patient_id")
        status = _optional_nonempty_string(payload.get("status"), "status")
        arm_id = _optional_nonempty_string(payload.get("arm_id"), "arm_id")
        source = _optional_nonempty_string(payload.get("source"), "source")
        failure_reason = _optional_nonempty_string(
            payload.get("failure_reason"), "failure_reason"
        )
        demographics = _optional_mapping(payload.get("demographics"), "demographics")
        baseline = _optional_mapping(payload.get("baseline"), "baseline")
        metadata = _optional_mapping(payload.get("metadata"), "metadata")
        auto_enroll = bool(payload.get("auto_enroll", False))

        try:
            return self.bridge.record_clinical_screening(
                trial_id=trial_id,
                site_id=site_id,
                patient_id=patient_id,
                status=status,
                arm_id=arm_id,
                source=source,
                failure_reason=failure_reason,
                demographics=demographics,
                baseline=baseline,
                metadata=metadata,
                auto_enroll=auto_enroll,
            )
        except KeyError as exc:
            raise NotFoundError(f"Unknown trial_id: {trial_id}") from exc
        except ValueError as exc:
            raise BadRequestError(str(exc)) from exc

    def add_clinical_monitoring_visit(self, payload: dict[str, Any]) -> dict[str, Any]:
        trial_id = _require_nonempty_string(payload.get("trial_id"), "trial_id")
        site_id = _require_nonempty_string(payload.get("site_id"), "site_id")
        visit_type = _optional_nonempty_string(payload.get("visit_type"), "visit_type")
        findings_raw = payload.get("findings")
        findings: list[str] | None = None
        if findings_raw is not None:
            if not isinstance(findings_raw, list):
                raise BadRequestError("findings must be an array when provided")
            findings = [str(item) for item in findings_raw if isinstance(item, str)]

        action_items_raw = payload.get("action_items")
        action_items: list[Any] | None = None
        if action_items_raw is not None:
            if not isinstance(action_items_raw, list):
                raise BadRequestError("action_items must be an array when provided")
            action_items = action_items_raw

        risk_raw = payload.get("risk_score")
        risk_score: float | None = None
        if risk_raw is not None:
            risk_score = _coerce_float(risk_raw, "risk_score", minimum=0.0)
            if risk_score > 1.0:
                raise BadRequestError("risk_score must be <= 1.0")
        outcome = _optional_nonempty_string(payload.get("outcome"), "outcome")
        metadata = _optional_mapping(payload.get("metadata"), "metadata")

        try:
            return self.bridge.record_clinical_monitoring_visit(
                trial_id=trial_id,
                site_id=site_id,
                visit_type=visit_type,
                findings=findings,
                action_items=action_items,
                risk_score=risk_score,
                outcome=outcome,
                metadata=metadata,
            )
        except KeyError as exc:
            raise NotFoundError(f"Unknown trial_id: {trial_id}") from exc
        except ValueError as exc:
            raise BadRequestError(str(exc)) from exc

    def add_clinical_query(self, payload: dict[str, Any]) -> dict[str, Any]:
        trial_id = _require_nonempty_string(payload.get("trial_id"), "trial_id")
        patient_id = _optional_nonempty_string(payload.get("patient_id"), "patient_id")
        site_id = _optional_nonempty_string(payload.get("site_id"), "site_id")
        field_name = _optional_nonempty_string(payload.get("field_name"), "field_name")
        description = _require_nonempty_string(
            payload.get("description"), "description"
        )
        status = _optional_nonempty_string(payload.get("status"), "status")
        severity = _optional_nonempty_string(payload.get("severity"), "severity")
        assignee = _optional_nonempty_string(payload.get("assignee"), "assignee")
        due_at = _optional_nonempty_string(payload.get("due_at"), "due_at")
        metadata = _optional_mapping(payload.get("metadata"), "metadata")

        try:
            return self.bridge.add_clinical_query(
                trial_id=trial_id,
                patient_id=patient_id,
                site_id=site_id,
                field_name=field_name,
                description=description,
                status=status,
                severity=severity,
                assignee=assignee,
                due_at=due_at,
                metadata=metadata,
            )
        except KeyError as exc:
            raise NotFoundError(f"Unknown trial_id: {trial_id}") from exc
        except ValueError as exc:
            raise BadRequestError(str(exc)) from exc

    def update_clinical_query(self, payload: dict[str, Any]) -> dict[str, Any]:
        trial_id = _require_nonempty_string(payload.get("trial_id"), "trial_id")
        query_id = _require_nonempty_string(payload.get("query_id"), "query_id")
        updates = payload.get("updates")
        if not isinstance(updates, dict):
            raise BadRequestError("updates must be a JSON object")
        try:
            return self.bridge.update_clinical_query(
                trial_id=trial_id,
                query_id=query_id,
                updates=updates,
            )
        except KeyError as exc:
            if str(exc).strip("'") == query_id:
                raise NotFoundError(f"Unknown query_id: {query_id}") from exc
            raise NotFoundError(f"Unknown trial_id: {trial_id}") from exc
        except ValueError as exc:
            raise BadRequestError(str(exc)) from exc

    def add_clinical_deviation(self, payload: dict[str, Any]) -> dict[str, Any]:
        trial_id = _require_nonempty_string(payload.get("trial_id"), "trial_id")
        description = _require_nonempty_string(
            payload.get("description"), "description"
        )
        site_id = _optional_nonempty_string(payload.get("site_id"), "site_id")
        patient_id = _optional_nonempty_string(payload.get("patient_id"), "patient_id")
        category = _optional_nonempty_string(payload.get("category"), "category")
        severity = _optional_nonempty_string(payload.get("severity"), "severity")
        status = _optional_nonempty_string(payload.get("status"), "status")
        corrective_action = _optional_nonempty_string(
            payload.get("corrective_action"),
            "corrective_action",
        )
        preventive_action = _optional_nonempty_string(
            payload.get("preventive_action"),
            "preventive_action",
        )
        metadata = _optional_mapping(payload.get("metadata"), "metadata")
        try:
            return self.bridge.add_clinical_deviation(
                trial_id=trial_id,
                description=description,
                site_id=site_id,
                patient_id=patient_id,
                category=category,
                severity=severity,
                status=status,
                corrective_action=corrective_action,
                preventive_action=preventive_action,
                metadata=metadata,
            )
        except KeyError as exc:
            raise NotFoundError(f"Unknown trial_id: {trial_id}") from exc
        except ValueError as exc:
            raise BadRequestError(str(exc)) from exc

    def add_clinical_safety_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        trial_id = _require_nonempty_string(payload.get("trial_id"), "trial_id")
        patient_id = _require_nonempty_string(payload.get("patient_id"), "patient_id")
        event_term = _require_nonempty_string(payload.get("event_term"), "event_term")
        site_id = _optional_nonempty_string(payload.get("site_id"), "site_id")
        seriousness = _optional_nonempty_string(
            payload.get("seriousness"), "seriousness"
        )
        expected_raw = payload.get("expected")
        expected: bool | None = None
        if expected_raw is not None:
            expected = bool(expected_raw)
        relatedness = _optional_nonempty_string(
            payload.get("relatedness"), "relatedness"
        )
        outcome = _optional_nonempty_string(payload.get("outcome"), "outcome")
        action_taken = _optional_nonempty_string(
            payload.get("action_taken"), "action_taken"
        )
        metadata = _optional_mapping(payload.get("metadata"), "metadata")
        try:
            return self.bridge.add_clinical_safety_event(
                trial_id=trial_id,
                patient_id=patient_id,
                event_term=event_term,
                site_id=site_id,
                seriousness=seriousness,
                expected=expected,
                relatedness=relatedness,
                outcome=outcome,
                action_taken=action_taken,
                metadata=metadata,
            )
        except KeyError as exc:
            raise NotFoundError(f"Unknown trial_id: {trial_id}") from exc
        except ValueError as exc:
            raise BadRequestError(str(exc)) from exc

    def upsert_clinical_milestone(self, payload: dict[str, Any]) -> dict[str, Any]:
        trial_id = _require_nonempty_string(payload.get("trial_id"), "trial_id")
        milestone_id = _optional_nonempty_string(
            payload.get("milestone_id"), "milestone_id"
        )
        name = _optional_nonempty_string(payload.get("name"), "name")
        target_date = _optional_nonempty_string(
            payload.get("target_date"), "target_date"
        )
        status = _optional_nonempty_string(payload.get("status"), "status")
        owner = _optional_nonempty_string(payload.get("owner"), "owner")
        actual_date = _optional_nonempty_string(
            payload.get("actual_date"), "actual_date"
        )
        metadata = _optional_mapping(payload.get("metadata"), "metadata")
        try:
            return self.bridge.upsert_clinical_milestone(
                trial_id=trial_id,
                milestone_id=milestone_id,
                name=name,
                target_date=target_date,
                status=status,
                owner=owner,
                actual_date=actual_date,
                metadata=metadata,
            )
        except KeyError as exc:
            raise NotFoundError(f"Unknown trial_id: {trial_id}") from exc
        except ValueError as exc:
            raise BadRequestError(str(exc)) from exc

    def preclinical_templates(self) -> dict[str, Any]:
        try:
            return self.bridge.preclinical_templates()
        except Exception as exc:  # noqa: BLE001
            raise BadRequestError(str(exc)) from exc

    def preclinical_cmc_templates(self) -> dict[str, Any]:
        try:
            return self.bridge.preclinical_cmc_templates()
        except Exception as exc:  # noqa: BLE001
            raise BadRequestError(str(exc)) from exc

    def preclinical_plan(self, payload: dict[str, Any]) -> dict[str, Any]:
        study = payload.get("study")
        if not isinstance(study, dict):
            raise BadRequestError("study must be a JSON object")
        seed = _coerce_int(payload.get("seed", 7), "seed")
        try:
            return self.bridge.preclinical_plan(study=study, seed=seed)
        except Exception as exc:  # noqa: BLE001
            raise BadRequestError(str(exc)) from exc

    def preclinical_schedule(self, payload: dict[str, Any]) -> dict[str, Any]:
        study = payload.get("study")
        if not isinstance(study, dict):
            raise BadRequestError("study must be a JSON object")
        try:
            return self.bridge.preclinical_schedule(study=study)
        except Exception as exc:  # noqa: BLE001
            raise BadRequestError(str(exc)) from exc

    def preclinical_bioanalysis(self, payload: dict[str, Any]) -> dict[str, Any]:
        study = payload.get("study")
        if not isinstance(study, dict):
            raise BadRequestError("study must be a JSON object")
        rows = payload.get("rows")
        if not isinstance(rows, list):
            raise BadRequestError("rows must be an array of sample objects")
        normalized_rows = [item for item in rows if isinstance(item, dict)]
        lloq_ng_ml = _coerce_float(
            payload.get("lloq_ng_ml", 1.0), "lloq_ng_ml", minimum=0.0
        )
        try:
            return self.bridge.preclinical_bioanalysis(
                study=study,
                rows=normalized_rows,
                lloq_ng_ml=lloq_ng_ml,
            )
        except Exception as exc:  # noqa: BLE001
            raise BadRequestError(str(exc)) from exc

    def preclinical_workup(self, payload: dict[str, Any]) -> dict[str, Any]:
        study = payload.get("study")
        if not isinstance(study, dict):
            raise BadRequestError("study must be a JSON object")
        rows_raw = payload.get("rows")
        rows: list[dict[str, Any]] | None = None
        if rows_raw is not None:
            if not isinstance(rows_raw, list):
                raise BadRequestError("rows must be an array when provided")
            rows = [item for item in rows_raw if isinstance(item, dict)]
        seed = _coerce_int(payload.get("seed", 7), "seed")
        lloq_ng_ml = _coerce_float(
            payload.get("lloq_ng_ml", 1.0), "lloq_ng_ml", minimum=0.0
        )
        cmc_config = _optional_mapping(payload.get("cmc_config"), "cmc_config")

        stability_results_raw = payload.get("stability_results")
        stability_results: list[dict[str, Any]] | None = None
        if stability_results_raw is not None:
            if not isinstance(stability_results_raw, list):
                raise BadRequestError(
                    "stability_results must be an array when provided"
                )
            stability_results = [
                item for item in stability_results_raw if isinstance(item, dict)
            ]

        batch_results_raw = payload.get("batch_results")
        batch_results: dict[str, Any] | list[dict[str, Any]] | None = None
        if batch_results_raw is not None:
            if isinstance(batch_results_raw, dict):
                batch_results = batch_results_raw
            elif isinstance(batch_results_raw, list):
                batch_results = [
                    item for item in batch_results_raw if isinstance(item, dict)
                ]
            else:
                raise BadRequestError(
                    "batch_results must be an object or array when provided"
                )

        batch_id = (
            _optional_nonempty_string(payload.get("batch_id"), "batch_id")
            or "BATCH-001"
        )
        try:
            return self.bridge.preclinical_workup(
                study=study,
                rows=rows,
                seed=seed,
                lloq_ng_ml=lloq_ng_ml,
                cmc_config=cmc_config,
                stability_results=stability_results,
                batch_results=batch_results,
                batch_id=batch_id,
            )
        except Exception as exc:  # noqa: BLE001
            raise BadRequestError(str(exc)) from exc

    def preclinical_cmc_plan(self, payload: dict[str, Any]) -> dict[str, Any]:
        cmc_config = _optional_mapping(payload.get("cmc_config"), "cmc_config")
        try:
            return self.bridge.preclinical_cmc_plan(cmc_config=cmc_config)
        except Exception as exc:  # noqa: BLE001
            raise BadRequestError(str(exc)) from exc

    def preclinical_batch_record(self, payload: dict[str, Any]) -> dict[str, Any]:
        cmc_config = _optional_mapping(payload.get("cmc_config"), "cmc_config")
        batch_id = (
            _optional_nonempty_string(payload.get("batch_id"), "batch_id")
            or "BATCH-001"
        )
        operator = (
            _optional_nonempty_string(payload.get("operator"), "operator") or "TBD"
        )
        site = _optional_nonempty_string(payload.get("site"), "site") or "TBD"
        manufacture_date = _optional_nonempty_string(
            payload.get("manufacture_date"),
            "manufacture_date",
        )
        try:
            return self.bridge.preclinical_batch_record(
                cmc_config=cmc_config,
                batch_id=batch_id,
                operator=operator,
                site=site,
                manufacture_date=manufacture_date,
            )
        except Exception as exc:  # noqa: BLE001
            raise BadRequestError(str(exc)) from exc

    def preclinical_stability_plan(self, payload: dict[str, Any]) -> dict[str, Any]:
        cmc_config = _optional_mapping(payload.get("cmc_config"), "cmc_config")
        batch_ids_raw = payload.get("batch_ids")
        batch_ids: list[str] | None = None
        if batch_ids_raw is not None:
            if not isinstance(batch_ids_raw, list):
                raise BadRequestError("batch_ids must be an array when provided")
            batch_ids = [
                str(item).strip() for item in batch_ids_raw if str(item).strip()
            ]
        try:
            return self.bridge.preclinical_stability_plan(
                cmc_config=cmc_config,
                batch_ids=batch_ids,
            )
        except Exception as exc:  # noqa: BLE001
            raise BadRequestError(str(exc)) from exc

    def preclinical_stability_assess(self, payload: dict[str, Any]) -> dict[str, Any]:
        cmc_config = _optional_mapping(payload.get("cmc_config"), "cmc_config")
        rows_raw = payload.get("rows")
        if not isinstance(rows_raw, list):
            raise BadRequestError("rows must be an array of stability result objects")
        rows = [item for item in rows_raw if isinstance(item, dict)]
        try:
            return self.bridge.preclinical_stability_assess(
                cmc_config=cmc_config,
                rows=rows,
            )
        except Exception as exc:  # noqa: BLE001
            raise BadRequestError(str(exc)) from exc

    def preclinical_release_assess(self, payload: dict[str, Any]) -> dict[str, Any]:
        cmc_config = _optional_mapping(payload.get("cmc_config"), "cmc_config")
        batch_results_raw = payload.get("batch_results")
        if isinstance(batch_results_raw, dict):
            batch_results: dict[str, Any] | list[dict[str, Any]] = batch_results_raw
        elif isinstance(batch_results_raw, list):
            batch_results = [
                item for item in batch_results_raw if isinstance(item, dict)
            ]
        else:
            raise BadRequestError("batch_results must be an object or array of objects")

        stability_results_raw = payload.get("stability_results")
        stability_results: list[dict[str, Any]] | None = None
        if stability_results_raw is not None:
            if not isinstance(stability_results_raw, list):
                raise BadRequestError(
                    "stability_results must be an array when provided"
                )
            stability_results = [
                item for item in stability_results_raw if isinstance(item, dict)
            ]
        try:
            return self.bridge.preclinical_release_assess(
                cmc_config=cmc_config,
                batch_results=batch_results,
                stability_results=stability_results,
            )
        except Exception as exc:  # noqa: BLE001
            raise BadRequestError(str(exc)) from exc


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


def _optional_mapping(value: Any, field_name: str) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise BadRequestError(f"{field_name} must be a JSON object when provided")
    return value


def _coerce_int(value: Any, field_name: str, *, minimum: int = 0) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise BadRequestError(f"{field_name} must be an integer") from exc
    if parsed < minimum:
        raise BadRequestError(f"{field_name} must be >= {minimum}")
    return parsed


def _coerce_float(value: Any, field_name: str, *, minimum: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise BadRequestError(f"{field_name} must be a number") from exc
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


def _query_optional_string(
    query: dict[str, list[str]],
    *,
    name: str,
) -> str | None:
    raw_values = query.get(name) or []
    if not raw_values:
        return None
    value = raw_values[0].strip()
    return value or None


def _optional_string_list(value: Any, field_name: str) -> list[str] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise BadRequestError(f"{field_name} must be an array of strings when provided")
    normalized: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str):
            raise BadRequestError(f"{field_name}[{index}] must be a string")
        stripped = item.strip()
        if not stripped:
            raise BadRequestError(f"{field_name}[{index}] must be non-empty")
        normalized.append(stripped)
    return normalized


def _to_metric_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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
    if path.startswith("/api/programs/") and path.endswith("/approve"):
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
            {
                "error": "Missing bearer token.",
                "required_role": required_role,
            },
        )

    token_roles = app.config.roles_for_token(token)
    if not token_roles:
        return (
            HTTPStatus.UNAUTHORIZED,
            {
                "error": "Invalid bearer token.",
                "required_role": required_role,
            },
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
            # Keep server logs quiet unless explicit debugging is needed.
            return

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path

            try:
                auth_failure = _authorize_request(
                    self, app, method="GET", path=path
                )
                if auth_failure is not None:
                    status, payload = auth_failure
                    _json_response(self, status, payload)
                    return

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
                if path == "/api/command-center/capabilities":
                    _json_response(
                        self, HTTPStatus.OK, app.command_center_capabilities_payload()
                    )
                    return
                if path == "/api/program-gates/templates":
                    _json_response(self, HTTPStatus.OK, app.stage_gate_templates())
                    return
                if path == "/api/programs":
                    query = parse_qs(parsed.query, keep_blank_values=False)
                    _json_response(self, HTTPStatus.OK, app.list_programs(query=query))
                    return
                if path.startswith("/api/programs/"):
                    query = parse_qs(parsed.query, keep_blank_values=False)
                    parts = [token for token in path.split("/") if token]
                    if len(parts) < 3:
                        raise BadRequestError("program_id is required")
                    program_id = parts[2]
                    if len(parts) == 3:
                        _json_response(
                            self,
                            HTTPStatus.OK,
                            app.get_program(program_id, query=query),
                        )
                        return
                    if len(parts) == 4 and parts[3] == "events":
                        _json_response(
                            self,
                            HTTPStatus.OK,
                            app.list_program_events(program_id, query=query),
                        )
                        return
                    if len(parts) == 4 and parts[3] == "approvals":
                        _json_response(
                            self,
                            HTTPStatus.OK,
                            app.list_program_approvals(program_id, query=query),
                        )
                        return
                    raise NotFoundError("unknown program endpoint")
                if path == "/api/data/datasets":
                    query = parse_qs(parsed.query, keep_blank_values=False)
                    _json_response(self, HTTPStatus.OK, app.data_datasets(query=query))
                    return
                if path == "/api/wetlab/providers":
                    _json_response(self, HTTPStatus.OK, app.wetlab_providers())
                    return
                if path == "/api/regulatory/bundles":
                    query = parse_qs(parsed.query, keep_blank_values=False)
                    _json_response(
                        self, HTTPStatus.OK, app.list_regulatory_bundles(query=query)
                    )
                    return
                if path == "/api/drug-portfolio":
                    query = parse_qs(parsed.query, keep_blank_values=False)
                    _json_response(self, HTTPStatus.OK, app.drug_portfolio(query=query))
                    return
                if path == "/api/promising-cures":
                    query = parse_qs(parsed.query, keep_blank_values=False)
                    _json_response(
                        self, HTTPStatus.OK, app.promising_cures(query=query)
                    )
                    return
                if path == "/api/clinical/trials":
                    _json_response(self, HTTPStatus.OK, app.clinical_trials())
                    return
                if path == "/api/preclinical/templates":
                    _json_response(self, HTTPStatus.OK, app.preclinical_templates())
                    return
                if path == "/api/preclinical/cmc/templates":
                    _json_response(self, HTTPStatus.OK, app.preclinical_cmc_templates())
                    return
                if path.startswith("/api/clinical/trials/"):
                    parts = [token for token in path.split("/") if token]
                    if len(parts) < 4:
                        raise BadRequestError("trial_id is required")
                    trial_id = parts[3]
                    if len(parts) == 4:
                        _json_response(
                            self, HTTPStatus.OK, app.clinical_trial(trial_id)
                        )
                        return
                    if len(parts) == 5 and parts[4] == "sites":
                        _json_response(
                            self, HTTPStatus.OK, app.clinical_trial_sites(trial_id)
                        )
                        return
                    if len(parts) == 5 and parts[4] == "ops":
                        _json_response(
                            self, HTTPStatus.OK, app.clinical_trial_ops(trial_id)
                        )
                        return
                    raise NotFoundError("unknown clinical trial endpoint")
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
                auth_failure = _authorize_request(
                    self, app, method="POST", path=path
                )
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
                if path == "/api/portfolio/rank":
                    _json_response(self, HTTPStatus.OK, app.rank_portfolio(payload))
                    return
                if path == "/api/programs/upsert":
                    _json_response(self, HTTPStatus.OK, app.upsert_program(payload))
                    return
                if path == "/api/programs/sync-jobs":
                    _json_response(self, HTTPStatus.OK, app.sync_program_jobs(payload))
                    return
                if path.startswith("/api/programs/"):
                    parts = [token for token in path.split("/") if token]
                    if len(parts) < 4:
                        raise BadRequestError("program_id and action are required")
                    program_id = parts[2]
                    action = parts[3]
                    if action == "events" and len(parts) == 5 and parts[4] == "add":
                        _json_response(
                            self,
                            HTTPStatus.OK,
                            app.add_program_event(program_id, payload),
                        )
                        return
                    if action == "approve" and len(parts) == 4:
                        _json_response(
                            self,
                            HTTPStatus.OK,
                            app.add_program_approval(program_id, payload),
                        )
                        return
                    if action == "gate-evaluate" and len(parts) == 4:
                        _json_response(
                            self,
                            HTTPStatus.OK,
                            app.evaluate_program_gate(program_id, payload),
                        )
                        return
                    raise NotFoundError("unknown program action")
                if path == "/api/data/materialize":
                    _json_response(self, HTTPStatus.OK, app.data_materialize(payload))
                    return
                if path == "/api/bench/gate":
                    _json_response(self, HTTPStatus.OK, app.benchmark_gate(payload))
                    return
                if path == "/api/wetlab/protocol/validate":
                    _json_response(
                        self, HTTPStatus.OK, app.wetlab_validate_protocol(payload)
                    )
                    return
                if path == "/api/wetlab/protocol/compile":
                    _json_response(
                        self, HTTPStatus.OK, app.wetlab_compile_protocol(payload)
                    )
                    return
                if path == "/api/wetlab/run":
                    _json_response(self, HTTPStatus.OK, app.wetlab_run(payload))
                    return
                if path == "/api/regulatory/bundle/build":
                    _json_response(
                        self, HTTPStatus.OK, app.build_regulatory_bundle(payload)
                    )
                    return
                if path == "/api/regulatory/bundle/verify":
                    _json_response(
                        self, HTTPStatus.OK, app.verify_regulatory_bundle(payload)
                    )
                    return
                if path == "/api/clawcures/handoff":
                    _json_response(self, HTTPStatus.OK, app.clawcures_handoff(payload))
                    return
                if path == "/api/clinical/trials/add":
                    _json_response(self, HTTPStatus.OK, app.add_clinical_trial(payload))
                    return
                if path == "/api/clinical/trials/update":
                    _json_response(
                        self, HTTPStatus.OK, app.update_clinical_trial(payload)
                    )
                    return
                if path == "/api/clinical/trials/remove":
                    _json_response(
                        self, HTTPStatus.OK, app.remove_clinical_trial(payload)
                    )
                    return
                if path == "/api/clinical/trials/enroll":
                    _json_response(
                        self, HTTPStatus.OK, app.enroll_clinical_patient(payload)
                    )
                    return
                if path == "/api/clinical/trials/enroll-simulated":
                    _json_response(
                        self,
                        HTTPStatus.OK,
                        app.enroll_simulated_clinical_patients(payload),
                    )
                    return
                if path == "/api/clinical/trials/result":
                    _json_response(
                        self, HTTPStatus.OK, app.add_clinical_result(payload)
                    )
                    return
                if path == "/api/clinical/trials/simulate":
                    _json_response(
                        self, HTTPStatus.OK, app.simulate_clinical_trial(payload)
                    )
                    return
                if path == "/api/clinical/trials/site/upsert":
                    _json_response(
                        self, HTTPStatus.OK, app.upsert_clinical_site(payload)
                    )
                    return
                if path == "/api/clinical/trials/screen":
                    _json_response(
                        self, HTTPStatus.OK, app.add_clinical_screening(payload)
                    )
                    return
                if path == "/api/clinical/trials/monitoring/visit":
                    _json_response(
                        self, HTTPStatus.OK, app.add_clinical_monitoring_visit(payload)
                    )
                    return
                if path == "/api/clinical/trials/query/add":
                    _json_response(self, HTTPStatus.OK, app.add_clinical_query(payload))
                    return
                if path == "/api/clinical/trials/query/update":
                    _json_response(
                        self, HTTPStatus.OK, app.update_clinical_query(payload)
                    )
                    return
                if path == "/api/clinical/trials/deviation/add":
                    _json_response(
                        self, HTTPStatus.OK, app.add_clinical_deviation(payload)
                    )
                    return
                if path == "/api/clinical/trials/safety/add":
                    _json_response(
                        self, HTTPStatus.OK, app.add_clinical_safety_event(payload)
                    )
                    return
                if path == "/api/clinical/trials/milestone/upsert":
                    _json_response(
                        self, HTTPStatus.OK, app.upsert_clinical_milestone(payload)
                    )
                    return
                if path == "/api/preclinical/plan":
                    _json_response(self, HTTPStatus.OK, app.preclinical_plan(payload))
                    return
                if path == "/api/preclinical/schedule":
                    _json_response(
                        self, HTTPStatus.OK, app.preclinical_schedule(payload)
                    )
                    return
                if path == "/api/preclinical/bioanalysis":
                    _json_response(
                        self, HTTPStatus.OK, app.preclinical_bioanalysis(payload)
                    )
                    return
                if path == "/api/preclinical/workup":
                    _json_response(self, HTTPStatus.OK, app.preclinical_workup(payload))
                    return
                if path == "/api/preclinical/cmc/plan":
                    _json_response(
                        self, HTTPStatus.OK, app.preclinical_cmc_plan(payload)
                    )
                    return
                if path == "/api/preclinical/cmc/batch-record":
                    _json_response(
                        self, HTTPStatus.OK, app.preclinical_batch_record(payload)
                    )
                    return
                if path == "/api/preclinical/cmc/stability-plan":
                    _json_response(
                        self, HTTPStatus.OK, app.preclinical_stability_plan(payload)
                    )
                    return
                if path == "/api/preclinical/cmc/stability-assess":
                    _json_response(
                        self, HTTPStatus.OK, app.preclinical_stability_assess(payload)
                    )
                    return
                if path == "/api/preclinical/cmc/release-assess":
                    _json_response(
                        self, HTTPStatus.OK, app.preclinical_release_assess(payload)
                    )
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

                _json_response(
                    self, HTTPStatus.NOT_FOUND, {"error": "unknown endpoint"}
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
