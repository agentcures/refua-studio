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
        "id": "refua_preclinical",
        "name": "refua-preclinical",
        "repo": "refua-preclinical",
        "module": "refua_preclinical",
        "role": "Preclinical tox/pharmacology planning and bioanalysis",
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
    {
        "id": "refua_wetlab",
        "name": "refua-wetlab",
        "repo": "refua-wetlab",
        "module": "refua_wetlab",
        "role": "Wet-lab protocol orchestration and execution",
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
            ("refua-clinical", "src"),
            ("refua-preclinical", "src"),
            ("refua-data", "src"),
            ("refua-bench", "src"),
            ("refua-regulatory", "src"),
            ("refua-wetlab", "src"),
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
        tool_names = sorted(set(adapter.available_tools()) | set(STATIC_TOOL_LIST))
        return tool_names, warnings

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

    def _clinical_controller(self) -> Any:
        clinical_mod = self._import("refua_campaign.clinical_trials")
        return clinical_mod.ClawCuresClinicalController(workspace_root=self._workspace_root)

    def list_clinical_trials(self) -> dict[str, Any]:
        controller = self._clinical_controller()
        return _to_plain_data(controller.list_trials())

    def get_clinical_trial(self, *, trial_id: str) -> dict[str, Any]:
        controller = self._clinical_controller()
        return _to_plain_data(controller.get_trial(trial_id))

    def add_clinical_trial(
        self,
        *,
        trial_id: str | None,
        config: dict[str, Any] | None,
        indication: str | None,
        phase: str | None,
        objective: str | None,
        status: str | None,
        metadata: dict[str, Any] | None,
    ) -> dict[str, Any]:
        controller = self._clinical_controller()
        return _to_plain_data(
            controller.add_trial(
                trial_id=trial_id,
                config=config,
                indication=indication,
                phase=phase,
                objective=objective,
                status=status,
                metadata=metadata,
            )
        )

    def update_clinical_trial(self, *, trial_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        controller = self._clinical_controller()
        return _to_plain_data(controller.update_trial(trial_id, updates=updates))

    def remove_clinical_trial(self, *, trial_id: str) -> dict[str, Any]:
        controller = self._clinical_controller()
        return _to_plain_data(controller.remove_trial(trial_id))

    def enroll_clinical_patient(
        self,
        *,
        trial_id: str,
        patient_id: str | None,
        source: str | None,
        arm_id: str | None,
        site_id: str | None = None,
        demographics: dict[str, Any] | None = None,
        baseline: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        controller = self._clinical_controller()
        return _to_plain_data(
            controller.enroll_patient(
                trial_id,
                patient_id=patient_id,
                source=source,
                arm_id=arm_id,
                site_id=site_id,
                demographics=demographics,
                baseline=baseline,
                metadata=metadata,
            )
        )

    def enroll_simulated_clinical_patients(
        self,
        *,
        trial_id: str,
        count: int,
        seed: int | None,
    ) -> dict[str, Any]:
        controller = self._clinical_controller()
        return _to_plain_data(
            controller.enroll_simulated_patients(
                trial_id,
                count=count,
                seed=seed,
            )
        )

    def add_clinical_result(
        self,
        *,
        trial_id: str,
        patient_id: str,
        values: dict[str, Any],
        result_type: str,
        visit: str | None,
        source: str | None,
        site_id: str | None = None,
    ) -> dict[str, Any]:
        controller = self._clinical_controller()
        return _to_plain_data(
            controller.add_result(
                trial_id,
                patient_id=patient_id,
                values=values,
                result_type=result_type,
                visit=visit,
                source=source,
                site_id=site_id,
            )
        )

    def simulate_clinical_trial(
        self,
        *,
        trial_id: str,
        replicates: int | None,
        seed: int | None,
    ) -> dict[str, Any]:
        controller = self._clinical_controller()
        return _to_plain_data(
            controller.simulate_trial(
                trial_id,
                replicates=replicates,
                seed=seed,
            )
        )

    def list_clinical_sites(self, *, trial_id: str) -> dict[str, Any]:
        controller = self._clinical_controller()
        return _to_plain_data(controller.list_sites(trial_id))

    def clinical_ops_snapshot(self, *, trial_id: str) -> dict[str, Any]:
        controller = self._clinical_controller()
        return _to_plain_data(controller.operations_snapshot(trial_id))

    def upsert_clinical_site(
        self,
        *,
        trial_id: str,
        site_id: str,
        name: str | None,
        country_id: str | None,
        status: str | None,
        principal_investigator: str | None,
        target_enrollment: int | None,
        metadata: dict[str, Any] | None,
    ) -> dict[str, Any]:
        controller = self._clinical_controller()
        return _to_plain_data(
            controller.upsert_site(
                trial_id,
                site_id=site_id,
                name=name,
                country_id=country_id,
                status=status,
                principal_investigator=principal_investigator,
                target_enrollment=target_enrollment,
                metadata=metadata,
            )
        )

    def record_clinical_screening(
        self,
        *,
        trial_id: str,
        site_id: str,
        patient_id: str | None,
        status: str | None,
        arm_id: str | None,
        source: str | None,
        failure_reason: str | None,
        demographics: dict[str, Any] | None,
        baseline: dict[str, Any] | None,
        metadata: dict[str, Any] | None,
        auto_enroll: bool,
    ) -> dict[str, Any]:
        controller = self._clinical_controller()
        return _to_plain_data(
            controller.record_screening(
                trial_id,
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
        )

    def record_clinical_monitoring_visit(
        self,
        *,
        trial_id: str,
        site_id: str,
        visit_type: str | None,
        findings: list[str] | None,
        action_items: list[Any] | None,
        risk_score: float | None,
        outcome: str | None,
        metadata: dict[str, Any] | None,
    ) -> dict[str, Any]:
        controller = self._clinical_controller()
        return _to_plain_data(
            controller.record_monitoring_visit(
                trial_id,
                site_id=site_id,
                visit_type=visit_type,
                findings=findings,
                action_items=action_items,
                risk_score=risk_score,
                outcome=outcome,
                metadata=metadata,
            )
        )

    def add_clinical_query(
        self,
        *,
        trial_id: str,
        patient_id: str | None,
        site_id: str | None,
        field_name: str | None,
        description: str,
        status: str | None,
        severity: str | None,
        assignee: str | None,
        due_at: str | None,
        metadata: dict[str, Any] | None,
    ) -> dict[str, Any]:
        controller = self._clinical_controller()
        return _to_plain_data(
            controller.add_query(
                trial_id,
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
        )

    def update_clinical_query(
        self,
        *,
        trial_id: str,
        query_id: str,
        updates: dict[str, Any],
    ) -> dict[str, Any]:
        controller = self._clinical_controller()
        return _to_plain_data(
            controller.update_query(
                trial_id,
                query_id=query_id,
                updates=updates,
            )
        )

    def add_clinical_deviation(
        self,
        *,
        trial_id: str,
        description: str,
        site_id: str | None,
        patient_id: str | None,
        category: str | None,
        severity: str | None,
        status: str | None,
        corrective_action: str | None,
        preventive_action: str | None,
        metadata: dict[str, Any] | None,
    ) -> dict[str, Any]:
        controller = self._clinical_controller()
        return _to_plain_data(
            controller.add_deviation(
                trial_id,
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
        )

    def add_clinical_safety_event(
        self,
        *,
        trial_id: str,
        patient_id: str,
        event_term: str,
        site_id: str | None,
        seriousness: str | None,
        expected: bool | None,
        relatedness: str | None,
        outcome: str | None,
        action_taken: str | None,
        metadata: dict[str, Any] | None,
    ) -> dict[str, Any]:
        controller = self._clinical_controller()
        return _to_plain_data(
            controller.add_safety_event(
                trial_id,
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
        )

    def upsert_clinical_milestone(
        self,
        *,
        trial_id: str,
        milestone_id: str | None,
        name: str | None,
        target_date: str | None,
        status: str | None,
        owner: str | None,
        actual_date: str | None,
        metadata: dict[str, Any] | None,
    ) -> dict[str, Any]:
        controller = self._clinical_controller()
        return _to_plain_data(
            controller.upsert_milestone(
                trial_id,
                milestone_id=milestone_id,
                name=name,
                target_date=target_date,
                status=status,
                owner=owner,
                actual_date=actual_date,
                metadata=metadata,
            )
        )

    def preclinical_templates(self) -> dict[str, Any]:
        pre_mod = self._import("refua_preclinical")
        templates = pre_mod.default_templates()
        references = pre_mod.latest_preclinical_references()
        return {
            "templates": _to_plain_data(templates),
            "references": _to_plain_data(references),
            "version": getattr(pre_mod, "__version__", None),
        }

    def preclinical_plan(
        self,
        *,
        study: dict[str, Any],
        seed: int,
    ) -> dict[str, Any]:
        pre_mod = self._import("refua_preclinical")
        spec = pre_mod.study_spec_from_mapping(study)
        plan = pre_mod.build_study_plan(spec, seed=int(seed))
        return {
            "study_id": spec.study_id,
            "plan": _to_plain_data(plan),
            "version": getattr(pre_mod, "__version__", None),
        }

    def preclinical_schedule(
        self,
        *,
        study: dict[str, Any],
    ) -> dict[str, Any]:
        pre_mod = self._import("refua_preclinical")
        spec = pre_mod.study_spec_from_mapping(study)
        schedule = pre_mod.build_in_vivo_schedule(spec)
        return {
            "study_id": spec.study_id,
            "schedule": _to_plain_data(schedule),
            "version": getattr(pre_mod, "__version__", None),
        }

    def preclinical_bioanalysis(
        self,
        *,
        study: dict[str, Any],
        rows: list[dict[str, Any]],
        lloq_ng_ml: float,
    ) -> dict[str, Any]:
        pre_mod = self._import("refua_preclinical")
        spec = pre_mod.study_spec_from_mapping(study)
        payload = pre_mod.run_bioanalytical_pipeline(
            spec,
            rows,
            lloq_ng_ml=float(lloq_ng_ml),
        )
        return {
            "study_id": spec.study_id,
            "bioanalysis": _to_plain_data(payload),
            "version": getattr(pre_mod, "__version__", None),
        }

    def preclinical_workup(
        self,
        *,
        study: dict[str, Any],
        rows: list[dict[str, Any]] | None,
        seed: int,
        lloq_ng_ml: float,
    ) -> dict[str, Any]:
        pre_mod = self._import("refua_preclinical")
        spec = pre_mod.study_spec_from_mapping(study)
        payload = pre_mod.build_workup(
            spec,
            samples=rows,
            seed=int(seed),
            lloq_ng_ml=float(lloq_ng_ml),
        )
        return {
            "study_id": spec.study_id,
            "workup": _to_plain_data(payload),
            "version": getattr(pre_mod, "__version__", None),
        }

    def _resolve_workspace_path(self, raw_path: str) -> Path:
        candidate = Path(raw_path).expanduser()
        if not candidate.is_absolute():
            candidate = self._workspace_root / candidate
        return candidate.resolve()

    def command_center_capabilities(self) -> dict[str, Any]:
        checks: tuple[tuple[str, str], ...] = (
            ("refua_data", "dataset_registry"),
            ("refua_preclinical", "preclinical_operations"),
            ("refua_bench", "benchmark_gating"),
            ("refua_regulatory", "regulatory_evidence"),
            ("refua_wetlab", "wetlab_orchestration"),
        )

        integrations: list[dict[str, Any]] = []
        warnings: list[str] = []
        for module_name, capability in checks:
            payload = {
                "module": module_name,
                "capability": capability,
                "available": False,
                "version": None,
            }
            try:
                module = self._import(module_name)
                payload["available"] = True
                payload["version"] = getattr(module, "__version__", None)
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"{module_name} unavailable: {exc}")
            integrations.append(payload)

        return {
            "generated_at": datetime.now(UTC).isoformat(),
            "integrations": integrations,
            "warnings": warnings,
        }

    def list_data_datasets(
        self,
        *,
        tag: str | None,
        limit: int,
    ) -> dict[str, Any]:
        warnings: list[str] = []
        try:
            refua_data_mod = self._import("refua_data")
            manager = refua_data_mod.DatasetManager()
            datasets = manager.list_datasets(tag=tag)
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"Fell back to static catalog because refua_data import failed: {exc}")
            catalog_mod = self._import("refua_data.catalog")
            catalog = catalog_mod.get_default_catalog()
            datasets = catalog.filter_by_tag(tag) if tag else catalog.list()
        snapshots = [item.metadata_snapshot() for item in datasets]
        safe_limit = min(max(int(limit), 1), 2000)
        selected = snapshots[:safe_limit]
        payload = {
            "count": len(selected),
            "total": len(snapshots),
            "tag": tag,
            "datasets": selected,
        }
        if warnings:
            payload["warnings"] = warnings
        return payload

    def materialize_dataset(
        self,
        *,
        dataset_id: str,
        force: bool,
        refresh: bool,
        chunksize: int,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        refua_data_mod = self._import("refua_data")
        manager = refua_data_mod.DatasetManager()
        result = manager.materialize(
            dataset_id,
            force=force,
            refresh=refresh,
            chunksize=int(chunksize),
            timeout_seconds=float(timeout_seconds),
        )
        provenance_mod = self._import("refua_data.provenance")
        provenance = provenance_mod.summarize_materialized_dataset(result.manifest_path)
        return {
            "dataset_id": dataset_id,
            "materialize": _to_plain_data(result),
            "provenance": _to_plain_data(provenance),
        }

    def gate_benchmark(
        self,
        *,
        suite_path: str,
        baseline_run_path: str,
        adapter_spec: str,
        adapter_config: dict[str, Any] | None,
        model_name: str | None,
        model_version: str | None,
        min_effect_size: float,
        bootstrap_resamples: int,
        confidence_level: float,
        bootstrap_seed: int | None,
        fail_on_uncertain: bool,
        candidate_output_path: str | None,
        comparison_output_path: str | None,
    ) -> dict[str, Any]:
        gating_mod = self._import("refua_bench.gating")
        compare_mod = self._import("refua_bench.compare")
        policy = compare_mod.StatisticalPolicy(
            min_effect_size=float(min_effect_size),
            bootstrap_resamples=int(bootstrap_resamples),
            confidence_level=float(confidence_level),
            bootstrap_seed=bootstrap_seed,
            fail_on_uncertain=bool(fail_on_uncertain),
        )

        provenance = {
            "model": {
                "name": model_name,
                "version": model_version,
            }
        }
        if model_name is None and model_version is None:
            provenance = {}

        normalized_adapter_config: dict[str, Any] | None = None
        if adapter_config is not None:
            normalized_adapter_config = dict(adapter_config)
            predictions_path = normalized_adapter_config.get("predictions_path")
            if (
                isinstance(predictions_path, str)
                and predictions_path.strip()
                and adapter_spec == "file"
            ):
                normalized_adapter_config["predictions_path"] = str(
                    self._resolve_workspace_path(predictions_path)
                )
        else:
            normalized_adapter_config = None

        payload = gating_mod.gate_suite(
            suite_path=self._resolve_workspace_path(suite_path),
            baseline_run_path=self._resolve_workspace_path(baseline_run_path),
            adapter_spec=adapter_spec,
            adapter_config=normalized_adapter_config,
            policy=policy,
            provenance=provenance,
            candidate_output_path=(
                self._resolve_workspace_path(candidate_output_path)
                if isinstance(candidate_output_path, str) and candidate_output_path.strip()
                else None
            ),
            comparison_output_path=(
                self._resolve_workspace_path(comparison_output_path)
                if isinstance(comparison_output_path, str) and comparison_output_path.strip()
                else None
            ),
        )
        return _to_plain_data(payload)

    def wetlab_providers(self) -> dict[str, Any]:
        engine_mod = self._import("refua_wetlab.engine")
        engine = engine_mod.UnifiedWetLabEngine()
        providers = engine.list_providers()
        return {
            "providers": _to_plain_data(providers),
            "count": len(providers),
        }

    def wetlab_validate_protocol(self, *, protocol: dict[str, Any]) -> dict[str, Any]:
        engine_mod = self._import("refua_wetlab.engine")
        engine = engine_mod.UnifiedWetLabEngine()
        normalized = engine.validate_protocol(protocol)
        return {
            "valid": True,
            "protocol": _to_plain_data(normalized),
        }

    def wetlab_compile_protocol(
        self,
        *,
        provider: str,
        protocol: dict[str, Any],
    ) -> dict[str, Any]:
        engine_mod = self._import("refua_wetlab.engine")
        engine = engine_mod.UnifiedWetLabEngine()
        payload = engine.compile_protocol(provider_id=provider, protocol_payload=protocol)
        return _to_plain_data(payload)

    def wetlab_run_protocol(
        self,
        *,
        provider: str,
        protocol: dict[str, Any],
        dry_run: bool,
        metadata: dict[str, Any] | None,
    ) -> dict[str, Any]:
        engine_mod = self._import("refua_wetlab.engine")
        lineage_mod = self._import("refua_wetlab.lineage")
        engine = engine_mod.UnifiedWetLabEngine()
        result = engine.run_protocol(
            provider_id=provider,
            protocol_payload=protocol,
            dry_run=bool(dry_run),
            metadata=metadata or {},
        )
        lineage = lineage_mod.build_wetlab_lineage_event(result)
        return {
            "result": _to_plain_data(result),
            "lineage_event": _to_plain_data(lineage),
        }

    def build_regulatory_bundle(
        self,
        *,
        campaign_run: dict[str, Any],
        output_dir: str,
        data_manifest_paths: list[str] | None,
        extra_artifacts: list[str] | None,
        include_checklists: bool,
        checklist_templates: list[str] | None,
        checklist_strict: bool,
        checklist_require_no_manual_review: bool,
        overwrite: bool,
    ) -> dict[str, Any]:
        studio_mod = self._import("refua_regulatory.studio")
        resolved_output_dir = self._resolve_workspace_path(output_dir)
        resolved_data = [
            self._resolve_workspace_path(path) for path in (data_manifest_paths or [])
        ]
        resolved_extras = [
            self._resolve_workspace_path(path) for path in (extra_artifacts or [])
        ]
        manifest = studio_mod.build_evidence_bundle_from_payload(
            campaign_run=campaign_run,
            output_dir=resolved_output_dir,
            source_kind="refua-studio",
            data_manifest_paths=resolved_data,
            extra_artifacts=resolved_extras,
            include_checklists=bool(include_checklists),
            checklist_templates=checklist_templates,
            checklist_strict=bool(checklist_strict),
            checklist_require_no_manual_review=bool(checklist_require_no_manual_review),
            overwrite=bool(overwrite),
        )
        verification = studio_mod.verify_bundle_with_summary(resolved_output_dir)
        return {
            "bundle_dir": str(resolved_output_dir),
            "manifest": _to_plain_data(manifest),
            "verification": _to_plain_data(verification.get("verification", {})),
            "summary": _to_plain_data(verification.get("summary", {})),
        }

    def verify_regulatory_bundle(self, *, bundle_dir: str) -> dict[str, Any]:
        studio_mod = self._import("refua_regulatory.studio")
        payload = studio_mod.verify_bundle_with_summary(
            self._resolve_workspace_path(bundle_dir)
        )
        return _to_plain_data(payload)
