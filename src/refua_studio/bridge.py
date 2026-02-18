from __future__ import annotations

import importlib
import json
import sys
from dataclasses import asdict, is_dataclass
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
    {
        "id": "oncology_infectious",
        "label": "Mixed portfolio",
        "objective": (
            "Build a high-impact portfolio balancing oncology and infectious disease programs "
            "using burden, tractability, unmet need, and safety signals."
        ),
    },
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
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, dict):
        return {str(k): _to_plain_data(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_plain_data(item) for item in value]
    if isinstance(value, tuple):
        return [_to_plain_data(item) for item in value]
    return value


class CampaignBridge:
    """Bridge from Studio to existing ClawCures/refua-mcp modules."""

    def __init__(self, workspace_root: Path) -> None:
        self._workspace_root = workspace_root
        self._paths_ready = False

    def _ensure_paths(self) -> None:
        if self._paths_ready:
            return
        for relative in (
            ("ClawCures", "src"),
            ("refua-mcp", "src"),
            ("refua", "src"),
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

    def _read_json_file(self, path: Path) -> tuple[Any | None, str | None]:
        if not path.exists():
            return None, f"Missing file: {path}"
        try:
            text = path.read_text(encoding="utf-8")
            return json.loads(text), None
        except Exception as exc:  # noqa: BLE001
            return None, f"Failed reading {path}: {exc}"

    def examples(self) -> dict[str, Any]:
        warnings: list[str] = []
        plan_templates: list[dict[str, Any]] = []
        portfolio_templates: list[dict[str, Any]] = []

        campaign_examples = self._workspace_root / "ClawCures" / "examples"

        plan_template_path = campaign_examples / "plan_template.json"
        plan_data, plan_error = self._read_json_file(plan_template_path)
        if plan_error is not None:
            warnings.append(plan_error)
        elif isinstance(plan_data, dict):
            plan_templates.append(
                {
                    "id": "campaign_plan_template",
                    "label": "Campaign Plan Template",
                    "description": "Default ClawCures example plan.",
                    "plan": plan_data,
                }
            )

        portfolio_input_path = campaign_examples / "portfolio_input.json"
        portfolio_data, portfolio_error = self._read_json_file(portfolio_input_path)
        if portfolio_error is not None:
            warnings.append(portfolio_error)
        elif isinstance(portfolio_data, list):
            portfolio_templates.append(
                {
                    "id": "campaign_portfolio_template",
                    "label": "Campaign Portfolio Template",
                    "description": "Default ClawCures example portfolio scoring input.",
                    "programs": portfolio_data,
                }
            )

        plan_templates.append(
            {
                "id": "validate_only_minimal",
                "label": "Validate-Only Minimal",
                "description": "Small, low-cost validator-first plan.",
                "plan": {
                    "calls": [
                        {
                            "tool": "refua_validate_spec",
                            "args": {
                                "action": "fold",
                                "name": "studio_validate_minimal",
                                "entities": [
                                    {
                                        "type": "protein",
                                        "id": "A",
                                        "sequence": "MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQ",
                                    },
                                    {"type": "ligand", "id": "lig", "smiles": "CCO"},
                                ],
                            },
                        }
                    ]
                },
            }
        )

        return {
            "objectives": list(_DEFAULT_OBJECTIVES),
            "plan_templates": plan_templates,
            "portfolio_templates": portfolio_templates,
            "warnings": warnings,
        }

    def available_tools(self) -> tuple[list[str], list[str]]:
        adapter, error = self._build_adapter()
        warnings: list[str] = []
        if error is not None:
            warnings.append(
                "Falling back to static tool list because refua-mcp runtime is unavailable: "
                f"{error}"
            )
        return sorted(adapter.available_tools()), warnings

    def runtime_config(self) -> dict[str, Any]:
        config_mod = self._import("refua_campaign.config")
        cfg = config_mod.OpenClawConfig.from_env()
        return {
            "openclaw": {
                "base_url": cfg.base_url,
                "model": cfg.model,
                "timeout_seconds": cfg.timeout_seconds,
                "has_token": bool(cfg.bearer_token),
            }
        }

    def plan(self, *, objective: str, system_prompt: str | None = None) -> dict[str, Any]:
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

        results = adapter.execute_plan(plan)
        return {
            "plan": _to_plain_data(plan),
            "results": [
                {
                    "tool": item.tool,
                    "args": _to_plain_data(item.args),
                    "output": _to_plain_data(item.output),
                }
                for item in results
            ],
        }

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

        prompts_mod = self._import("refua_campaign.prompts")
        orchestrator_mod = self._import("refua_campaign.orchestrator")
        openclaw_mod = self._import("refua_campaign.openclaw_client")
        config_mod = self._import("refua_campaign.config")

        resolved_prompt = system_prompt or prompts_mod.load_system_prompt()
        adapter, adapter_error = self._build_adapter()
        orchestrator = orchestrator_mod.CampaignOrchestrator(
            openclaw=openclaw_mod.OpenClawClient(config_mod.OpenClawConfig.from_env()),
            refua_mcp=adapter,
        )

        planner_text = ""
        if plan is not None:
            if not isinstance(plan, dict):
                raise ValueError("plan must be a JSON object")
            resolved_plan = plan
            planner_text = "Loaded from request"
        else:
            planner_text, resolved_plan = orchestrator.plan(
                objective=objective_text,
                system_prompt=resolved_prompt,
            )

        payload: dict[str, Any] = {
            "objective": objective_text,
            "system_prompt": resolved_prompt,
            "planner_response_text": planner_text,
            "plan": _to_plain_data(resolved_plan),
            "dry_run": bool(dry_run),
        }

        if dry_run:
            if adapter_error is not None:
                payload["warnings"] = [adapter_error]
            return payload

        if adapter_error is not None:
            raise StudioBridgeError(adapter_error)

        results = orchestrator.execute_plan(resolved_plan)
        payload["results"] = [
            {
                "tool": item.tool,
                "args": _to_plain_data(item.args),
                "output": _to_plain_data(item.output),
            }
            for item in results
        ]
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
        tools = sorted(adapter.available_tools())
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
                openclaw=openclaw_mod.OpenClawClient(config_mod.OpenClawConfig.from_env()),
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

        if dry_run:
            return payload

        if not bool(payload.get("approved", False)):
            return payload

        if adapter_error is not None:
            raise StudioBridgeError(adapter_error)

        final_plan = payload.get("final_plan")
        if not isinstance(final_plan, dict):
            raise StudioBridgeError("Autonomous planner did not produce a valid final_plan.")

        results = adapter.execute_plan(final_plan)
        payload["results"] = [
            {
                "tool": item.tool,
                "args": _to_plain_data(item.args),
                "output": _to_plain_data(item.output),
            }
            for item in results
        ]
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

        autonomy_mod = self._import("refua_campaign.autonomy")
        tools, warnings = self.available_tools()
        policy = autonomy_mod.PlanPolicy(
            max_calls=int(max_calls),
            require_validate_first=not allow_skip_validate_first,
        )
        check = autonomy_mod.evaluate_plan_policy(
            plan,
            allowed_tools=tools,
            policy=policy,
        )
        payload: dict[str, Any] = {
            "approved": bool(check.approved),
            "errors": list(check.errors),
            "warnings": list(check.warnings),
            "allowed_tools": tools,
            "policy": {
                "max_calls": int(max_calls),
                "require_validate_first": not allow_skip_validate_first,
            },
        }
        if warnings:
            payload.setdefault("bridge_warnings", []).extend(warnings)
        return payload

    def rank_portfolio(
        self,
        *,
        programs: list[dict[str, Any]],
        weights: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        portfolio_mod = self._import("refua_campaign.portfolio")
        kwargs = {}
        if weights:
            kwargs = {k: float(v) for k, v in weights.items()}
        weights_obj = portfolio_mod.PortfolioWeights(**kwargs)
        ranked = portfolio_mod.rank_disease_programs(programs, weights=weights_obj)
        return {
            "weights": _to_plain_data(weights_obj),
            "ranked": [entry.to_json() for entry in ranked],
        }
