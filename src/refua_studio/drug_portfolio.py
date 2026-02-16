from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True)
class DrugCandidate:
    candidate_id: str
    name: str | None
    smiles: str | None
    target: str | None
    tool: str
    score: float
    promising: bool
    metrics: dict[str, float | None]
    assessment: str | None
    source_job_id: str
    source_kind: str
    source_updated_at: str
    objective: str | None
    evidence_paths: dict[str, str]
    tool_args: dict[str, Any]
    tool_output: Any

    def to_json(self, *, include_raw: bool) -> dict[str, Any]:
        payload = {
            "candidate_id": self.candidate_id,
            "name": self.name,
            "smiles": self.smiles,
            "target": self.target,
            "tool": self.tool,
            "score": self.score,
            "promising": self.promising,
            "metrics": self.metrics,
            "assessment": self.assessment,
            "source": {
                "job_id": self.source_job_id,
                "kind": self.source_kind,
                "updated_at": self.source_updated_at,
                "objective": self.objective,
            },
            "evidence_paths": self.evidence_paths,
            "tool_args": self.tool_args,
        }
        if include_raw:
            payload["tool_output"] = self.tool_output
        return payload


def build_drug_portfolio(
    jobs: list[dict[str, Any]],
    *,
    limit: int = 100,
    min_score: float = 0.0,
    include_raw: bool = False,
) -> dict[str, Any]:
    candidates: list[DrugCandidate] = []

    for job in jobs:
        candidates.extend(_extract_candidates_from_job(job))

    min_score_value = max(float(min_score), 0.0)
    filtered = [candidate for candidate in candidates if candidate.score >= min_score_value]
    filtered.sort(key=lambda item: item.score, reverse=True)

    safe_limit = max(1, min(int(limit), 500))
    selected = filtered[:safe_limit]

    tool_counter = Counter(candidate.tool for candidate in selected)

    summary = {
        "generated_at": datetime.now(UTC).isoformat(),
        "total_candidates": len(candidates),
        "returned_candidates": len(selected),
        "min_score": min_score_value,
        "limit": safe_limit,
        "by_tool": dict(tool_counter),
        "promising_count": sum(1 for candidate in selected if candidate.promising),
    }

    return {
        "summary": summary,
        "candidates": [candidate.to_json(include_raw=include_raw) for candidate in selected],
    }


def _extract_candidates_from_job(job: dict[str, Any]) -> list[DrugCandidate]:
    status = str(job.get("status", ""))
    if status != "completed":
        return []

    result = job.get("result")
    if not isinstance(result, dict):
        return []

    tool_results = result.get("results")
    if not isinstance(tool_results, list):
        return []

    extracted: list[DrugCandidate] = []
    objective = None
    request = job.get("request")
    if isinstance(request, dict):
        maybe_objective = request.get("objective")
        if isinstance(maybe_objective, str) and maybe_objective.strip():
            objective = maybe_objective.strip()

    for index, item in enumerate(tool_results):
        if not isinstance(item, dict):
            continue
        candidate = _candidate_from_tool_result(
            job=job,
            objective=objective,
            tool_result=item,
            index=index,
        )
        if candidate is not None:
            extracted.append(candidate)

    return extracted


def _candidate_from_tool_result(
    *,
    job: dict[str, Any],
    objective: str | None,
    tool_result: dict[str, Any],
    index: int,
) -> DrugCandidate | None:
    flat: dict[str, Any] = {}

    tool = str(tool_result.get("tool") or "unknown_tool")
    args = tool_result.get("args")
    output = tool_result.get("output")

    _flatten(args, "args", flat)
    _flatten(output, "output", flat)

    evidence_paths: dict[str, str] = {}

    name, name_path = _pick_string(flat, [
        "name",
        "compound_name",
        "ligand_name",
        "candidate_name",
        "ligand",
        "binder",
    ])
    if name_path:
        evidence_paths["name"] = name_path

    smiles, smiles_path = _pick_string(flat, [
        "smiles",
        "ligand_smiles",
        "compound_smiles",
    ])
    if smiles_path:
        evidence_paths["smiles"] = smiles_path

    target, target_path = _pick_string(flat, [
        "target",
        "target_name",
        "protein",
        "antigen",
    ])
    if target_path:
        evidence_paths["target"] = target_path

    binding_probability, binding_path = _pick_float(flat, [
        "binding_probability",
        "probability",
        "p_bind",
        "predicted_probability",
    ])
    if binding_path:
        evidence_paths["binding_probability"] = binding_path

    admet_score, admet_path = _pick_float(flat, [
        "admet_score",
        "overall_score",
        "druglikeness",
    ])
    if admet_path:
        evidence_paths["admet_score"] = admet_path

    affinity, affinity_path = _pick_float(flat, [
        "affinity",
        "predicted_affinity",
        "delta_g",
    ])
    if affinity_path:
        evidence_paths["affinity"] = affinity_path

    ic50, ic50_path = _pick_float(flat, [
        "ic50",
        "predicted_ic50",
    ])
    if ic50_path:
        evidence_paths["ic50"] = ic50_path

    kd, kd_path = _pick_float(flat, [
        "kd",
        "predicted_kd",
    ])
    if kd_path:
        evidence_paths["kd"] = kd_path

    assessment, assessment_path = _pick_string(flat, [
        "assessment",
        "admet_assessment",
        "safety_assessment",
    ])
    if assessment_path:
        evidence_paths["assessment"] = assessment_path

    metrics = {
        "binding_probability": binding_probability,
        "admet_score": admet_score,
        "affinity": affinity,
        "ic50": ic50,
        "kd": kd,
    }

    has_signal = any(value is not None for value in metrics.values()) or smiles is not None
    if not has_signal:
        return None

    score = _score_candidate(metrics=metrics, assessment=assessment)
    job_id = str(job.get("job_id") or "unknown_job")

    return DrugCandidate(
        candidate_id=f"{job_id}:{index}",
        name=name,
        smiles=smiles,
        target=target,
        tool=tool,
        score=score,
        promising=score >= 50.0,
        metrics=metrics,
        assessment=assessment,
        source_job_id=job_id,
        source_kind=str(job.get("kind") or "unknown"),
        source_updated_at=str(job.get("updated_at") or ""),
        objective=objective,
        evidence_paths=evidence_paths,
        tool_args=args if isinstance(args, dict) else {},
        tool_output=output,
    )


def _score_candidate(*, metrics: dict[str, float | None], assessment: str | None) -> float:
    score = 0.0

    binding_probability = metrics.get("binding_probability")
    if binding_probability is not None:
        bp = binding_probability
        if bp > 1:
            bp = bp / 100.0
        score += 55.0 * _clamp01(bp)

    admet_score = metrics.get("admet_score")
    if admet_score is not None:
        ad = admet_score
        if ad > 1:
            ad = ad / 100.0
        score += 25.0 * _clamp01(ad)

    affinity = metrics.get("affinity")
    if affinity is not None:
        if affinity < 0:
            score += 12.0 * _clamp01((-affinity) / 15.0)
        else:
            score += 8.0 * _clamp01(affinity / 15.0)

    ic50 = metrics.get("ic50")
    if ic50 is not None and ic50 > 0:
        score += 8.0 * _potency_score(ic50)

    kd = metrics.get("kd")
    if kd is not None and kd > 0:
        score += 6.0 * _potency_score(kd)

    metric_count = sum(1 for value in metrics.values() if value is not None)
    score += min(metric_count, 5) * 1.5

    if assessment is not None:
        lowered = assessment.lower()
        if any(token in lowered for token in ("high risk", "unsafe", "toxic")):
            score -= 12.0
        elif any(token in lowered for token in ("favorable", "promising", "good")):
            score += 6.0

    return round(max(0.0, min(score, 100.0)), 2)


def _potency_score(value: float) -> float:
    # Robust generic transform: smaller positive values map to stronger scores.
    transformed = 1.0 / (1.0 + math.log10(value + 1.0))
    return _clamp01(transformed)


def _clamp01(value: float) -> float:
    if value < 0:
        return 0.0
    if value > 1:
        return 1.0
    return value


def _flatten(value: Any, prefix: str, out: dict[str, Any]) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            next_prefix = f"{prefix}.{key}" if prefix else str(key)
            _flatten(nested, next_prefix, out)
        return
    if isinstance(value, list):
        for idx, nested in enumerate(value):
            next_prefix = f"{prefix}[{idx}]"
            _flatten(nested, next_prefix, out)
        return
    if isinstance(value, (str, int, float, bool)) or value is None:
        out[prefix] = value


def _pick_string(flat: dict[str, Any], aliases: list[str]) -> tuple[str | None, str | None]:
    value, path = _pick_value(flat, aliases)
    if isinstance(value, str):
        cleaned = value.strip()
        if cleaned:
            return cleaned, path
    return None, None


def _pick_float(flat: dict[str, Any], aliases: list[str]) -> tuple[float | None, str | None]:
    value, path = _pick_value(flat, aliases)
    if isinstance(value, bool):
        return None, None
    if isinstance(value, (int, float)):
        return float(value), path
    if isinstance(value, str):
        try:
            return float(value.strip()), path
        except ValueError:
            return None, None
    return None, None


def _pick_value(flat: dict[str, Any], aliases: list[str]) -> tuple[Any | None, str | None]:
    # Prefer exact leaf-key matches first, then substring path matches.
    exact_hits: list[tuple[str, Any]] = []
    loose_hits: list[tuple[str, Any]] = []

    for path, value in flat.items():
        leaf = _leaf_token(path)
        lowered_leaf = leaf.lower()
        lowered_path = path.lower()

        for alias in aliases:
            alias_lower = alias.lower()
            if lowered_leaf == alias_lower:
                exact_hits.append((path, value))
                break
            if alias_lower in lowered_path:
                loose_hits.append((path, value))
                break

    if exact_hits:
        exact_hits.sort(key=lambda item: len(item[0]))
        return exact_hits[0][1], exact_hits[0][0]
    if loose_hits:
        loose_hits.sort(key=lambda item: len(item[0]))
        return loose_hits[0][1], loose_hits[0][0]
    return None, None


def _leaf_token(path: str) -> str:
    token = path
    if "." in token:
        token = token.rsplit(".", 1)[-1]
    if "[" in token:
        token = token.split("[", 1)[0]
    return token
