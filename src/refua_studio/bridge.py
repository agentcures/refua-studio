from __future__ import annotations

import importlib
import json
import shlex
import sys
import tomllib
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
    {
        "id": "oncology_infectious",
        "label": "Mixed portfolio",
        "objective": (
            "Build a high-impact portfolio balancing oncology and infectious disease programs "
            "using burden, tractability, unmet need, and safety signals."
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
        "cli": "ClawCures",
    },
    {
        "id": "refua_studio",
        "name": "refua-studio",
        "repo": "refua-studio",
        "module": "refua_studio",
        "role": "Web control plane",
        "cli": "refua-studio",
    },
    {
        "id": "refua_mcp",
        "name": "refua-mcp",
        "repo": "refua-mcp",
        "module": "refua_mcp",
        "role": "Typed scientific tool server",
    },
    {
        "id": "refua_core",
        "name": "refua",
        "repo": "refua",
        "module": "refua",
        "role": "Core molecular design and scoring",
    },
    {
        "id": "refua_data",
        "name": "refua-data",
        "repo": "refua-data",
        "module": "refua_data",
        "role": "Data and catalog pipeline",
    },
    {
        "id": "refua_clinical",
        "name": "refua-clinical",
        "repo": "refua-clinical",
        "module": "refua_clinical",
        "role": "Clinical simulation and translational modeling",
    },
    {
        "id": "refua_regulatory",
        "name": "refua-regulatory",
        "repo": "refua-regulatory",
        "module": "refua_regulatory",
        "role": "Regulatory lineage and evidence packaging",
    },
    {
        "id": "refua_bench",
        "name": "refua-bench",
        "repo": "refua-bench",
        "module": "refua_bench",
        "role": "Benchmark and evaluation harness",
    },
    {
        "id": "refua_notebook",
        "name": "refua-notebook",
        "repo": "refua-notebook",
        "module": "refua_notebook",
        "role": "Notebook widgets and exploratory workflows",
    },
    {
        "id": "refua_deploy",
        "name": "refua-deploy",
        "repo": "refua-deploy",
        "module": "refua_deploy",
        "role": "Deployment and environment rendering",
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

    def _read_json_file(self, path: Path) -> tuple[Any | None, str | None]:
        if not path.exists():
            return None, f"Missing file: {path}"
        try:
            text = path.read_text(encoding="utf-8")
            return json.loads(text), None
        except Exception as exc:  # noqa: BLE001
            return None, f"Failed reading {path}: {exc}"

    def _read_pyproject_meta(self, repo_dir: Path) -> dict[str, Any]:
        pyproject_path = repo_dir / "pyproject.toml"
        if not pyproject_path.exists():
            return {}
        try:
            parsed = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}
        project = parsed.get("project")
        if not isinstance(project, dict):
            return {}
        return {
            "name": project.get("name"),
            "version": project.get("version"),
            "requires_python": project.get("requires-python"),
        }

    def _load_product_status(self, descriptor: dict[str, str]) -> dict[str, Any]:
        repo_name = descriptor["repo"]
        repo_dir = self._workspace_root / repo_name
        pyproject = self._read_pyproject_meta(repo_dir)
        module_name = descriptor.get("module", "")

        imported = False
        module_file: str | None = None
        import_error: str | None = None
        if module_name:
            self._ensure_paths()
            try:
                spec = importlib.util.find_spec(module_name)
                imported = spec is not None
                if spec is not None and isinstance(spec.origin, str):
                    module_file = spec.origin
            except Exception as exc:  # noqa: BLE001
                import_error = f"{type(exc).__name__}: {exc}"

        exists = repo_dir.exists()
        ready = bool(exists and imported)
        health = "ready" if ready else "degraded" if exists else "missing"

        payload = {
            "id": descriptor["id"],
            "name": descriptor["name"],
            "role": descriptor["role"],
            "repo": repo_name,
            "path": str(repo_dir),
            "exists": exists,
            "health": health,
            "importable": imported,
            "module": module_name,
            "module_file": module_file,
            "readme_path": str(repo_dir / "README.md"),
            "version": pyproject.get("version"),
            "requires_python": pyproject.get("requires_python"),
        }
        cli = descriptor.get("cli")
        if cli:
            payload["cli"] = cli
        if import_error is not None:
            payload["import_error"] = import_error
        return payload

    def _clawcures_defaults(self) -> tuple[dict[str, Any], list[str]]:
        warnings: list[str] = []
        objective = _DEFAULT_CLAWCURES_OBJECTIVE
        prompt_text = ""
        allowlist: list[str] = list(STATIC_TOOL_LIST)
        prompt_path = self._workspace_root / "ClawCures" / "src" / "refua_campaign" / "prompts" / (
            "default_system_prompt.txt"
        )

        try:
            cli_mod = self._import("refua_campaign.cli")
            objective = str(getattr(cli_mod, "DEFAULT_OBJECTIVE", objective))
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"Could not import ClawCures default objective: {exc}")

        try:
            prompts_mod = self._import("refua_campaign.prompts")
            prompt_text = str(prompts_mod.load_system_prompt())
            config_mod = self._import("refua_campaign.config")
            prompt_path = config_mod.default_prompt_path()
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"Could not import ClawCures prompt loader: {exc}")
            if prompt_path.exists() and not prompt_text:
                try:
                    prompt_text = prompt_path.read_text(encoding="utf-8")
                except Exception as nested_exc:  # noqa: BLE001
                    warnings.append(f"Could not read default prompt file: {nested_exc}")

        try:
            adapter_mod = self._import("refua_campaign.refua_mcp_adapter")
            raw_allowlist = getattr(adapter_mod, "DEFAULT_TOOL_LIST", ())
            if isinstance(raw_allowlist, (list, tuple)):
                allowlist = [str(name) for name in raw_allowlist if isinstance(name, str)]
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"Could not load ClawCures tool allowlist: {exc}")

        prompt_lines = [line.strip() for line in prompt_text.splitlines() if line.strip()]
        prompt_preview = "\n".join(prompt_lines[:6])

        return (
            {
                "default_objective": objective,
                "default_prompt_path": str(prompt_path),
                "default_prompt_preview": prompt_preview,
                "default_prompt_line_count": len(prompt_lines),
                "tool_allowlist": sorted(set(allowlist)),
            },
            warnings,
        )

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

    def ecosystem(self) -> dict[str, Any]:
        warnings: list[str] = []
        products = [self._load_product_status(descriptor) for descriptor in _PRODUCT_REGISTRY]

        clawcures_defaults, clawcures_warnings = self._clawcures_defaults()
        warnings.extend(clawcures_warnings)

        return {
            "generated_at": datetime.now(UTC).isoformat(),
            "products": products,
            "clawcures": clawcures_defaults,
            "warnings": warnings,
        }

    def build_clawcures_handoff(
        self,
        *,
        objective: str | None,
        plan: dict[str, Any] | None,
        system_prompt: str | None,
        autonomous: bool,
        dry_run: bool,
        max_calls: int,
        allow_skip_validate_first: bool,
        write_file: bool,
        artifact_dir: Path,
        artifact_name: str | None = None,
    ) -> dict[str, Any]:
        clawcures_defaults, default_warnings = self._clawcures_defaults()
        resolved_objective = (
            objective.strip()
            if isinstance(objective, str) and objective.strip()
            else clawcures_defaults["default_objective"]
        )

        normalized_plan = _to_plain_data(plan) if isinstance(plan, dict) else None
        normalized_prompt = (
            system_prompt.strip() if isinstance(system_prompt, str) and system_prompt.strip() else None
        )
        mode_command = "run-autonomous" if autonomous else "run"

        artifact_payload: dict[str, Any] = {
            "generated_at": datetime.now(UTC).isoformat(),
            "source": "refua-studio",
            "objective": resolved_objective,
            "run_mode": mode_command,
            "dry_run": bool(dry_run),
            "max_calls": int(max_calls),
            "allow_skip_validate_first": bool(allow_skip_validate_first),
            "plan": normalized_plan,
            "system_prompt": normalized_prompt,
        }

        artifact_path: str | None = None
        if write_file:
            artifact_dir.mkdir(parents=True, exist_ok=True)
            filename = artifact_name or (
                "clawcures_handoff_" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + ".json"
            )
            if not filename.endswith(".json"):
                filename = f"{filename}.json"
            target_path = artifact_dir / filename
            target_path.write_text(
                json.dumps(artifact_payload, ensure_ascii=True, indent=2),
                encoding="utf-8",
            )
            artifact_path = str(target_path)

        command_flags = [f"--objective {shlex.quote(resolved_objective)}"]
        if dry_run:
            command_flags.append("--dry-run")
        if autonomous:
            command_flags.append(f"--max-calls {int(max_calls)}")
            if allow_skip_validate_first:
                command_flags.append("--allow-skip-validate-first")
        if artifact_path is not None and normalized_plan is not None:
            command_flags.append(f"--plan-file {shlex.quote(artifact_path)}")
        elif normalized_plan is not None:
            command_flags.append("--plan-file <handoff_plan.json>")

        run_command = " ".join(["ClawCures", mode_command, *command_flags])

        validate_command = "ClawCures validate-plan --plan-file "
        if artifact_path is not None and normalized_plan is not None:
            validate_command += shlex.quote(artifact_path)
        else:
            validate_command += "<handoff_plan.json>"

        payload: dict[str, Any] = {
            "artifact": artifact_payload,
            "artifact_path": artifact_path,
            "commands": [
                {
                    "id": "clawcures_run",
                    "label": f"Execute with ClawCures {mode_command}",
                    "command": run_command,
                },
                {
                    "id": "clawcures_validate",
                    "label": "Validate plan policy",
                    "command": validate_command,
                },
            ],
            "clawcures_defaults": clawcures_defaults,
            "warnings": default_warnings,
        }

        if normalized_plan is None:
            payload["warnings"].append(
                "No plan was provided in the handoff payload; ClawCures will plan at runtime."
            )

        return payload

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
        serialized_results = [
            {
                "tool": item.tool,
                "args": _to_plain_data(item.args),
                "output": _to_plain_data(item.output),
            }
            for item in results
        ]
        cures, cures_summary, cures_error = self._extract_promising_cures_from_results(
            serialized_results
        )

        payload: dict[str, Any] = {
            "plan": _to_plain_data(plan),
            "results": serialized_results,
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
        serialized_results = [
            {
                "tool": item.tool,
                "args": _to_plain_data(item.args),
                "output": _to_plain_data(item.output),
            }
            for item in results
        ]
        cures, cures_summary, cures_error = self._extract_promising_cures_from_results(
            serialized_results
        )
        payload["results"] = serialized_results
        payload["promising_cures"] = cures
        if cures_summary is not None:
            payload["promising_cures_summary"] = cures_summary
        if cures_error is not None:
            payload.setdefault("warnings", []).append(
                "Could not extract promising cures from execution results: "
                f"{cures_error}"
            )
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
        serialized_results = [
            {
                "tool": item.tool,
                "args": _to_plain_data(item.args),
                "output": _to_plain_data(item.output),
            }
            for item in results
        ]
        cures, cures_summary, cures_error = self._extract_promising_cures_from_results(
            serialized_results
        )
        payload["results"] = serialized_results
        payload["promising_cures"] = cures
        if cures_summary is not None:
            payload["promising_cures_summary"] = cures_summary
        if cures_error is not None:
            payload.setdefault("warnings", []).append(
                "Could not extract promising cures from autonomous execution results: "
                f"{cures_error}"
            )
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
