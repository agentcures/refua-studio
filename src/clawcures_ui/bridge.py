from __future__ import annotations

import importlib
import json
import sys
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

STATIC_TOOL_LIST = [
    "refua_validate_spec",
    "refua_fold",
    "refua_affinity",
    "refua_antibody_design",
    "refua_protein_properties",
    "refua_clinical_simulator",
    "refua_data_list",
    "refua_data_fetch",
    "refua_data_materialize",
    "refua_data_query",
    "refua_job",
    "refua_admet_profile",
]

_DEFAULT_OBJECTIVES: tuple[dict[str, str], ...] = (
    {
        "id": "kras_g12d",
        "label": "KRAS G12D bootstrap",
        "objective": (
            "Design an initial campaign against KRAS G12D with measurable milestones "
            "for target validation, binder design, and affinity prioritization."
        ),
    },
    {
        "id": "egfr_resistance",
        "label": "EGFR resistance campaign",
        "objective": (
            "Design a campaign for EGFR resistance variants with an explicit validation-first "
            "tool plan and translational readout strategy."
        ),
    },
)

_PRODUCT_REGISTRY: tuple[dict[str, str], ...] = (
    {
        "id": "clawcures",
        "name": "ClawCures",
        "repo": "ClawCures",
        "module": "refua_campaign",
        "role": "Campaign planner and execution orchestrator",
    },
    {
        "id": "clawcures_ui",
        "name": "clawcures-ui",
        "repo": "clawcures-ui",
        "module": "clawcures_ui",
        "role": "Web control plane",
    },
    {
        "id": "refua_mcp",
        "name": "refua-mcp",
        "repo": "refua-mcp",
        "module": "refua_mcp",
        "role": "Scientific tool server",
    },
    {
        "id": "refua_core",
        "name": "refua",
        "repo": "refua",
        "module": "refua",
        "role": "Core molecular design and scoring",
    },
)

_DEFAULT_CLAWCURES_OBJECTIVE = (
    "Find cures for all diseases by prioritizing the highest-burden conditions and "
    "researching the best drug design strategies for each."
)


class StudioBridgeError(RuntimeError):
    """Raised when bridge operations fail."""


class _StaticToolAdapter:
    def __init__(self, tool_names: list[str] | tuple[str, ...] | None = None) -> None:
        self._tool_names = list(tool_names) if tool_names else list(STATIC_TOOL_LIST)

    def available_tools(self) -> list[str]:
        return list(self._tool_names)

    def execute_plan(self, _plan: dict[str, object]) -> list[object]:
        raise RuntimeError(
            "Cannot execute plan because refua-mcp runtime dependencies are missing."
        )


def _to_plain_data(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, dict):
        return {str(key): _to_plain_data(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_plain_data(item) for item in value]
    if isinstance(value, tuple):
        return [_to_plain_data(item) for item in value]
    return value


class CampaignBridge:
    """Bridge from the web app to the live ClawCures orchestration layer."""

    def __init__(self, workspace_root: Path) -> None:
        self._workspace_root = workspace_root
        self._paths_ready = False

    def shutdown(self) -> None:
        return

    def _ensure_paths(self) -> None:
        if self._paths_ready:
            return
        for relative in (
            ("ClawCures", "src"),
            ("clawcures-ui", "src"),
            ("refua-studio", "src"),
            ("refua-mcp", "src"),
            ("refua", "src"),
            ("refua-clinical", "src"),
            ("refua-data", "src"),
        ):
            candidate = self._workspace_root.joinpath(*relative)
            if candidate.exists():
                candidate_text = str(candidate)
                if candidate_text not in sys.path:
                    sys.path.insert(0, candidate_text)
        self._paths_ready = True

    def _import(self, module_name: str) -> Any:
        self._ensure_paths()
        return importlib.import_module(module_name)

    def _build_adapter(self) -> tuple[Any, str | None]:
        fallback_tools = list(STATIC_TOOL_LIST)
        try:
            adapter_mod = self._import("refua_campaign.refua_mcp_adapter")
            adapter_fallback = getattr(adapter_mod, "DEFAULT_TOOL_LIST", None)
            if isinstance(adapter_fallback, (list, tuple)) and all(
                isinstance(item, str) for item in adapter_fallback
            ):
                fallback_tools = list(adapter_fallback)
            adapter = adapter_mod.RefuaMcpAdapter()
            return adapter, None
        except Exception as exc:  # noqa: BLE001
            return _StaticToolAdapter(fallback_tools), str(exc)

    def _planner_tool_allowlist(self) -> list[str]:
        allowlist = list(STATIC_TOOL_LIST)
        try:
            adapter_mod = self._import("refua_campaign.refua_mcp_adapter")
            raw_allowlist = getattr(adapter_mod, "DEFAULT_TOOL_LIST", ())
            if isinstance(raw_allowlist, (list, tuple)):
                filtered = [
                    str(name).strip()
                    for name in raw_allowlist
                    if isinstance(name, str) and str(name).strip()
                ]
                if filtered:
                    allowlist = filtered
        except Exception:
            pass
        try:
            adapter, error = self._build_adapter()
        except Exception:
            adapter = None
            error = None
        if error is None and adapter is not None:
            supported = set(adapter.available_tools())
            allowlist = [name for name in allowlist if name in supported]
        return sorted(dict.fromkeys(allowlist))

    def _read_text_file(self, path: Path) -> tuple[str | None, str | None]:
        if not path.exists():
            return None, f"Missing file: {path}"
        try:
            return path.read_text(encoding="utf-8"), None
        except Exception as exc:  # noqa: BLE001
            return None, f"Failed reading {path}: {exc}"

    def _serialize_results(self, results: list[Any]) -> list[dict[str, Any]]:
        payload: list[dict[str, Any]] = []
        for item in results:
            payload.append(
                {
                    "tool": getattr(item, "tool", None),
                    "args": _to_plain_data(getattr(item, "args", None)),
                    "output": _to_plain_data(getattr(item, "output", None)),
                }
            )
        return payload

    def _extract_promising_cures_from_results(
        self,
        serialized_results: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None, str | None]:
        try:
            cures_mod = self._import("refua_campaign.promising_cures")
            cures = cures_mod.extract_promising_cures(serialized_results)
            summary = cures_mod.summarize_promising_cures(cures)
            return cures, summary, None
        except Exception as exc:  # noqa: BLE001
            return [], None, str(exc)

    def _load_product_status(self, descriptor: dict[str, str]) -> dict[str, Any]:
        repo_dir = self._workspace_root / descriptor["repo"]
        module_name = descriptor.get("module", "")
        imported = False
        if module_name:
            self._ensure_paths()
            try:
                imported = importlib.util.find_spec(module_name) is not None
            except Exception:
                imported = False
        exists = repo_dir.exists()
        health = "healthy" if exists and imported else "degraded" if exists else "missing"
        return {
            "id": descriptor["id"],
            "name": descriptor["name"],
            "role": descriptor["role"],
            "repo": descriptor["repo"],
            "path": str(repo_dir),
            "health": health,
            "importable": imported,
        }

    def _clawcures_defaults(self) -> tuple[dict[str, Any], list[str]]:
        warnings: list[str] = []
        objective = _DEFAULT_CLAWCURES_OBJECTIVE
        prompt_text = ""
        prompt_path = (
            self._workspace_root
            / "ClawCures"
            / "src"
            / "refua_campaign"
            / "prompts"
            / "default_system_prompt.txt"
        )

        try:
            cli_mod = self._import("refua_campaign.cli")
            objective = str(getattr(cli_mod, "DEFAULT_OBJECTIVE", objective))
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"Could not import ClawCures default objective: {exc}")

        try:
            prompts_mod = self._import("refua_campaign.prompts")
            prompt_text = str(prompts_mod.load_system_prompt())
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"Could not import ClawCures prompt loader: {exc}")
            prompt_text, read_error = self._read_text_file(prompt_path)
            if read_error is not None:
                warnings.append(read_error)
                prompt_text = ""

        prompt_lines = [
            line.strip() for line in prompt_text.splitlines() if line.strip()
        ]
        return (
            {
                "default_objective": objective,
                "default_prompt_path": str(prompt_path),
                "default_prompt_preview": "\n".join(prompt_lines[:6]),
                "default_prompt_line_count": len(prompt_lines),
                "tool_allowlist": self._planner_tool_allowlist(),
            },
            warnings,
        )

    def default_objective(self) -> str:
        defaults, _warnings = self._clawcures_defaults()
        objective = defaults.get("default_objective")
        if isinstance(objective, str) and objective.strip():
            return objective
        return _DEFAULT_CLAWCURES_OBJECTIVE

    def examples(self) -> dict[str, Any]:
        return {
            "objectives": list(_DEFAULT_OBJECTIVES),
            "warnings": [],
        }

    def available_tools(self) -> tuple[list[str], list[str]]:
        adapter, error = self._build_adapter()
        warnings: list[str] = []
        if error is not None:
            warnings.append(
                "Falling back to static tool list because refua-mcp runtime is unavailable: "
                f"{error}"
            )
        tool_names = sorted(set(adapter.available_tools()) | set(STATIC_TOOL_LIST))
        return tool_names, warnings

    def ecosystem(self) -> dict[str, Any]:
        clawcures_defaults, warnings = self._clawcures_defaults()
        products = [
            self._load_product_status(descriptor) for descriptor in _PRODUCT_REGISTRY
        ]
        return {
            "generated_at": datetime.now(UTC).isoformat(),
            "products": products,
            "clawcures": clawcures_defaults,
            "warnings": warnings,
        }

    def plan(
        self, *, objective: str, system_prompt: str | None = None
    ) -> dict[str, Any]:
        objective_text = objective.strip()
        if not objective_text:
            raise ValueError("objective must be a non-empty string")

        prompts_mod = self._import("refua_campaign.prompts")
        orchestrator_mod = self._import("refua_campaign.orchestrator")
        openclaw_mod = self._import("refua_campaign.openclaw_client")
        config_mod = self._import("refua_campaign.config")

        resolved_prompt = system_prompt or prompts_mod.load_system_prompt()
        adapter, adapter_error = self._build_adapter()
        orchestrator = orchestrator_mod.CampaignOrchestrator(
            openclaw=openclaw_mod.OpenClawClient(config_mod.OpenClawConfig.from_env()),
            refua_mcp=adapter,
            planner_tools=self._planner_tool_allowlist(),
        )
        planner_text, plan = orchestrator.plan(
            objective=objective_text,
            system_prompt=resolved_prompt,
        )
        payload: dict[str, Any] = {
            "objective": objective_text,
            "system_prompt": resolved_prompt,
            "planner_response_text": planner_text,
            "plan": _to_plain_data(plan),
        }
        if adapter_error is not None:
            payload["warnings"] = [adapter_error]
        return payload

    def execute_plan(self, *, plan: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(plan, dict):
            raise ValueError("plan must be a JSON object")

        adapter, adapter_error = self._build_adapter()
        if adapter_error is not None:
            raise StudioBridgeError(adapter_error)

        results = self._serialize_results(adapter.execute_plan(plan))
        cures, cures_summary, cures_error = self._extract_promising_cures_from_results(
            results
        )
        payload: dict[str, Any] = {
            "plan": _to_plain_data(plan),
            "results": results,
            "promising_cures": cures,
        }
        if cures_summary is not None:
            payload["promising_cures_summary"] = cures_summary
        if cures_error is not None:
            payload.setdefault("warnings", []).append(
                "Could not extract promising cures from execution results: "
                f"{cures_error}"
            )
        return payload

    def run(
        self,
        *,
        objective: str,
        system_prompt: str | None = None,
        dry_run: bool = False,
        plan: dict[str, Any] | None = None,
        autonomous: bool = False,
        max_rounds: int = 3,
        max_calls: int = 10,
        allow_skip_validate_first: bool = False,
    ) -> dict[str, Any]:
        if autonomous:
            return self._run_autonomous(
                objective=objective,
                system_prompt=system_prompt,
                dry_run=dry_run,
                plan=plan,
                max_rounds=max_rounds,
                max_calls=max_calls,
                allow_skip_validate_first=allow_skip_validate_first,
            )
        return self._run_once(
            objective=objective,
            system_prompt=system_prompt,
            dry_run=dry_run,
            plan=plan,
        )

    def _run_once(
        self,
        *,
        objective: str,
        system_prompt: str | None,
        dry_run: bool,
        plan: dict[str, Any] | None,
    ) -> dict[str, Any]:
        objective_text = objective.strip()
        if not objective_text:
            raise ValueError("objective must be a non-empty string")

        if plan is not None and not isinstance(plan, dict):
            raise ValueError("plan must be a JSON object")

        prompts_mod = self._import("refua_campaign.prompts")
        resolved_prompt = system_prompt or prompts_mod.load_system_prompt()

        payload: dict[str, Any] = {
            "objective": objective_text,
            "system_prompt": resolved_prompt,
            "dry_run": bool(dry_run),
        }

        if plan is not None:
            resolved_plan = plan
            payload["planner_response_text"] = "Loaded from request"
        else:
            planner_payload = self.plan(
                objective=objective_text,
                system_prompt=resolved_prompt,
            )
            resolved_plan = planner_payload["plan"]
            payload["planner_response_text"] = planner_payload["planner_response_text"]
            if "warnings" in planner_payload:
                payload["warnings"] = list(planner_payload["warnings"])

        payload["plan"] = _to_plain_data(resolved_plan)
        if dry_run:
            return payload

        execution_payload = self.execute_plan(plan=resolved_plan)
        payload["results"] = execution_payload["results"]
        payload["promising_cures"] = execution_payload["promising_cures"]
        if "promising_cures_summary" in execution_payload:
            payload["promising_cures_summary"] = execution_payload[
                "promising_cures_summary"
            ]
        if "warnings" in execution_payload:
            payload.setdefault("warnings", []).extend(execution_payload["warnings"])
        return payload

    def _run_autonomous(
        self,
        *,
        objective: str,
        system_prompt: str | None,
        dry_run: bool,
        plan: dict[str, Any] | None,
        max_rounds: int,
        max_calls: int,
        allow_skip_validate_first: bool,
    ) -> dict[str, Any]:
        objective_text = objective.strip()
        if not objective_text:
            raise ValueError("objective must be a non-empty string")

        prompts_mod = self._import("refua_campaign.prompts")
        autonomy_mod = self._import("refua_campaign.autonomy")
        openclaw_mod = self._import("refua_campaign.openclaw_client")
        config_mod = self._import("refua_campaign.config")

        adapter, adapter_error = self._build_adapter()
        tools = self._planner_tool_allowlist()
        policy = autonomy_mod.PlanPolicy(
            max_calls=int(max_calls),
            require_validate_first=not allow_skip_validate_first,
        )
        resolved_prompt = system_prompt or prompts_mod.load_system_prompt()

        if plan is not None:
            if not isinstance(plan, dict):
                raise ValueError("plan must be a JSON object")
            policy_check = autonomy_mod.evaluate_plan_policy(
                plan,
                allowed_tools=tools,
                policy=policy,
            )
            payload: dict[str, Any] = {
                "objective": objective_text,
                "system_prompt": resolved_prompt,
                "approved": bool(policy_check.approved),
                "iterations": [],
                "final_plan": _to_plain_data(plan),
                "policy": {
                    "approved": bool(policy_check.approved),
                    "errors": list(policy_check.errors),
                    "warnings": list(policy_check.warnings),
                },
                "dry_run": bool(dry_run),
            }
        else:
            planner = autonomy_mod.AutonomousPlanner(
                openclaw=openclaw_mod.OpenClawClient(
                    config_mod.OpenClawConfig.from_env()
                ),
                available_tools=tools,
                policy=policy,
            )
            result = planner.run(
                objective=objective_text,
                system_prompt=resolved_prompt,
                max_rounds=int(max_rounds),
            )
            payload = _to_plain_data(result.to_json())
            payload["dry_run"] = bool(dry_run)

        if adapter_error is not None:
            payload.setdefault("warnings", []).append(adapter_error)

        if dry_run or not bool(payload.get("approved", False)):
            return payload

        if adapter_error is not None:
            raise StudioBridgeError(adapter_error)

        final_plan = payload.get("final_plan")
        if not isinstance(final_plan, dict):
            raise StudioBridgeError(
                "Autonomous planner did not produce a valid final_plan."
            )

        execution_payload = self.execute_plan(plan=final_plan)
        payload["results"] = execution_payload["results"]
        payload["promising_cures"] = execution_payload["promising_cures"]
        if "promising_cures_summary" in execution_payload:
            payload["promising_cures_summary"] = execution_payload[
                "promising_cures_summary"
            ]
        if "warnings" in execution_payload:
            payload.setdefault("warnings", []).extend(execution_payload["warnings"])
        return payload

    def validate_plan(
        self,
        *,
        plan: dict[str, Any],
        max_calls: int,
        allow_skip_validate_first: bool,
    ) -> dict[str, Any]:
        if not isinstance(plan, dict):
            raise ValueError("plan must be a JSON object")

        tools, warnings = self.available_tools()
        require_validate_first = not allow_skip_validate_first
        max_calls_int = int(max_calls)
        try:
            autonomy_mod = self._import("refua_campaign.autonomy")
            policy = autonomy_mod.PlanPolicy(
                max_calls=max_calls_int,
                require_validate_first=require_validate_first,
            )
            check = autonomy_mod.evaluate_plan_policy(
                plan,
                allowed_tools=tools,
                policy=policy,
            )
            errors = list(check.errors)
            check_warnings = list(check.warnings)
            approved = bool(check.approved)
        except ModuleNotFoundError as exc:
            if exc.name and not exc.name.startswith("refua_campaign"):
                raise
            calls = plan.get("calls")
            errors: list[str] = []
            check_warnings: list[str] = [
                (
                    "Using fallback plan validator because "
                    "refua_campaign.autonomy is unavailable."
                )
            ]
            if not isinstance(calls, list):
                errors.append("plan.calls must be a list")
                calls = []
            if len(calls) > max_calls_int:
                errors.append(
                    f"plan exceeds max_calls ({len(calls)} > {max_calls_int})"
                )
            if require_validate_first and calls:
                first_tool = calls[0].get("tool") if isinstance(calls[0], dict) else None
                if first_tool != "refua_validate_spec":
                    errors.append(
                        "first call must be refua_validate_spec when "
                        "require_validate_first is enabled"
                    )
            unknown_tools = [
                call.get("tool")
                for call in calls
                if isinstance(call, dict)
                and isinstance(call.get("tool"), str)
                and call.get("tool") not in tools
            ]
            if unknown_tools:
                errors.append(
                    "plan contains unsupported tools: "
                    + ", ".join(sorted({str(name) for name in unknown_tools}))
                )
            approved = len(errors) == 0

        payload: dict[str, Any] = {
            "approved": approved,
            "errors": errors,
            "warnings": check_warnings,
            "allowed_tools": tools,
            "policy": {
                "max_calls": max_calls_int,
                "require_validate_first": require_validate_first,
            },
        }
        if warnings:
            payload["bridge_warnings"] = warnings
        return payload
