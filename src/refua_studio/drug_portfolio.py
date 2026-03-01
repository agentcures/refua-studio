from __future__ import annotations

import math
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

_ADMET_HINTS: tuple[str, ...] = (
    "admet",
    "tox",
    "herg",
    "ames",
    "dili",
    "carcinogen",
    "clintox",
    "clearance",
    "half_life",
    "bioavailability",
    "solubility",
    "permeability",
    "cyp",
)


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
    admet: dict[str, Any]
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
            "admet": self.admet,
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
    filtered = [
        candidate for candidate in candidates if candidate.score >= min_score_value
    ]
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
        "with_admet_properties": sum(
            1
            for candidate in selected
            if isinstance(candidate.admet.get("properties"), Mapping)
            and bool(candidate.admet.get("properties"))
        ),
    }

    return {
        "summary": summary,
        "candidates": [
            candidate.to_json(include_raw=include_raw) for candidate in selected
        ],
    }


def _extract_candidates_from_job(job: dict[str, Any]) -> list[DrugCandidate]:
    status = str(job.get("status", ""))
    if status != "completed":
        return []

    result = job.get("result")
    if not isinstance(result, Mapping):
        return []

    objective = None
    request = job.get("request")
    if isinstance(request, Mapping):
        maybe_objective = request.get("objective")
        if isinstance(maybe_objective, str) and maybe_objective.strip():
            objective = maybe_objective.strip()

    extracted: list[DrugCandidate] = []

    promising_cures = result.get("promising_cures")
    if isinstance(promising_cures, list):
        for index, item in enumerate(promising_cures):
            if not isinstance(item, Mapping):
                continue
            candidate = _candidate_from_promising_cure(
                job=job,
                objective=objective,
                cure_payload=item,
                index=index,
            )
            if candidate is not None:
                extracted.append(candidate)

    tool_results = result.get("results")
    if isinstance(tool_results, list):
        existing_ids = {candidate.candidate_id for candidate in extracted}
        for index, item in enumerate(tool_results):
            if not isinstance(item, Mapping):
                continue
            candidate = _candidate_from_tool_result(
                job=job,
                objective=objective,
                tool_result=item,
                index=index,
            )
            if candidate is None:
                continue
            if candidate.candidate_id in existing_ids:
                continue
            extracted.append(candidate)

    return extracted


def _candidate_from_promising_cure(
    *,
    job: dict[str, Any],
    objective: str | None,
    cure_payload: Mapping[str, Any],
    index: int,
) -> DrugCandidate | None:
    metrics_payload = cure_payload.get("metrics")
    metrics = _coerce_metrics(
        metrics_payload if isinstance(metrics_payload, Mapping) else {}
    )

    admet_payload = _normalize_admet_payload(cure_payload.get("admet"))
    if metrics.get("admet_score") is None:
        metrics["admet_score"] = admet_payload["key_metrics"].get("admet_score")

    assessment = _optional_text(cure_payload.get("assessment"))
    if not assessment:
        assessment = _optional_text(admet_payload.get("assessment"))

    score = _coerce_score(
        cure_payload.get("score"), metrics=metrics, assessment=assessment
    )
    promising_raw = cure_payload.get("promising")
    if isinstance(promising_raw, bool):
        promising = promising_raw
    else:
        promising = score >= 50.0

    smiles = _optional_text(cure_payload.get("smiles"))
    has_signal = any(value is not None for value in metrics.values()) or bool(smiles)
    if not has_signal:
        return None

    cure_id = _optional_text(cure_payload.get("cure_id"))
    candidate_id = cure_id or f"{job.get('job_id', 'unknown_job')}:claw:{index}"

    evidence = cure_payload.get("evidence_paths")
    evidence_paths = dict(evidence) if isinstance(evidence, Mapping) else {}

    tool_args_raw = cure_payload.get("tool_args")
    tool_args = dict(tool_args_raw) if isinstance(tool_args_raw, Mapping) else {}

    return DrugCandidate(
        candidate_id=candidate_id,
        name=_optional_text(cure_payload.get("name")),
        smiles=smiles,
        target=_optional_text(cure_payload.get("target")),
        tool=_optional_text(cure_payload.get("tool")) or "unknown_tool",
        score=score,
        promising=promising,
        metrics=metrics,
        admet=admet_payload,
        assessment=assessment,
        source_job_id=str(job.get("job_id") or "unknown_job"),
        source_kind=str(job.get("kind") or "unknown"),
        source_updated_at=str(job.get("updated_at") or ""),
        objective=objective,
        evidence_paths=evidence_paths,
        tool_args=tool_args,
        tool_output=cure_payload,
    )


def _candidate_from_tool_result(
    *,
    job: dict[str, Any],
    objective: str | None,
    tool_result: Mapping[str, Any],
    index: int,
) -> DrugCandidate | None:
    flat: dict[str, Any] = {}

    tool = str(tool_result.get("tool") or "unknown_tool")
    args = tool_result.get("args")
    output = tool_result.get("output")

    _flatten(args, "args", flat)
    _flatten(output, "output", flat)

    evidence_paths: dict[str, str] = {}

    name, name_path = _pick_string(
        flat,
        [
            "name",
            "compound_name",
            "ligand_name",
            "candidate_name",
            "ligand",
            "binder",
        ],
    )
    if name_path:
        evidence_paths["name"] = name_path

    smiles, smiles_path = _pick_string(
        flat,
        [
            "smiles",
            "ligand_smiles",
            "compound_smiles",
        ],
    )
    if smiles_path:
        evidence_paths["smiles"] = smiles_path

    target, target_path = _pick_string(
        flat,
        [
            "target",
            "target_name",
            "protein",
            "antigen",
        ],
    )
    if target_path:
        evidence_paths["target"] = target_path

    binding_probability, binding_path = _pick_float(
        flat,
        [
            "binding_probability",
            "probability",
            "p_bind",
            "predicted_probability",
        ],
    )
    if binding_path:
        evidence_paths["binding_probability"] = binding_path

    affinity, affinity_path = _pick_float(
        flat,
        [
            "affinity",
            "predicted_affinity",
            "delta_g",
        ],
    )
    if affinity_path:
        evidence_paths["affinity"] = affinity_path

    ic50, ic50_path = _pick_float(flat, ["ic50", "predicted_ic50"])
    if ic50_path:
        evidence_paths["ic50"] = ic50_path

    kd, kd_path = _pick_float(flat, ["kd", "predicted_kd"])
    if kd_path:
        evidence_paths["kd"] = kd_path

    admet_payload = _normalize_admet_payload(output)
    admet_score = admet_payload["key_metrics"].get("admet_score")
    if admet_score is None:
        admet_score, admet_path = _pick_float(
            flat,
            [
                "admet_score",
                "overall_score",
                "druglikeness",
                "score_admet",
            ],
        )
        if admet_path:
            evidence_paths["admet_score"] = admet_path

    assessment, assessment_path = _pick_string(
        flat,
        [
            "assessment",
            "admet_assessment",
            "safety_assessment",
        ],
    )
    if assessment_path:
        evidence_paths["assessment"] = assessment_path
    if not assessment:
        assessment = _optional_text(admet_payload.get("assessment"))

    metrics = {
        "binding_probability": binding_probability,
        "admet_score": admet_score,
        "affinity": affinity,
        "ic50": ic50,
        "kd": kd,
    }

    has_signal = (
        any(value is not None for value in metrics.values())
        or smiles is not None
        or bool(admet_payload.get("properties"))
    )
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
        admet=admet_payload,
        assessment=assessment,
        source_job_id=job_id,
        source_kind=str(job.get("kind") or "unknown"),
        source_updated_at=str(job.get("updated_at") or ""),
        objective=objective,
        evidence_paths=evidence_paths,
        tool_args=dict(args) if isinstance(args, Mapping) else {},
        tool_output=output,
    )


def _normalize_admet_payload(value: Any) -> dict[str, Any]:
    flat: dict[str, Any] = {}
    _flatten(value, "", flat)

    properties: dict[str, float | str | bool | None] = {}
    for key, item in flat.items():
        if not _is_scalar(item):
            continue
        normalized_path = key.lower()
        if "raw_output" in normalized_path or "raw_outputs" in normalized_path:
            continue
        if not any(token in normalized_path for token in _ADMET_HINTS):
            continue
        if (
            normalized_path.startswith("key_metrics.")
            or ".key_metrics." in normalized_path
        ):
            continue
        normalized_key = key.strip(".")
        if normalized_key.startswith("admet."):
            normalized_key = normalized_key.removeprefix("admet.")
        if "admet." in normalized_key:
            normalized_key = normalized_key.split("admet.", 1)[1]
        if normalized_key.startswith("properties."):
            normalized_key = normalized_key.removeprefix("properties.")
        properties[normalized_key] = item

    key_metrics = {
        "admet_score": _resolve_metric(properties, "admet_score"),
        "safety_score": _resolve_metric(properties, "safety_score"),
        "adme_score": _resolve_metric(properties, "adme_score"),
        "rdkit_score": _resolve_metric(properties, "rdkit_score"),
    }

    assessment = None
    for key in (
        "assessment",
        "assessment_text",
        "admet_assessment",
        "safety_assessment",
    ):
        found = _resolve_text(properties, key)
        if found:
            assessment = found
            break

    status = None
    if isinstance(value, Mapping):
        status = _optional_text(value.get("status"))

    return {
        "status": status,
        "key_metrics": key_metrics,
        "assessment": assessment,
        "properties": properties,
    }


def _coerce_metrics(payload: Mapping[str, Any]) -> dict[str, float | None]:
    return {
        "binding_probability": _coerce_float(payload.get("binding_probability")),
        "admet_score": _coerce_float(payload.get("admet_score")),
        "affinity": _coerce_float(payload.get("affinity")),
        "ic50": _coerce_float(payload.get("ic50")),
        "kd": _coerce_float(payload.get("kd")),
    }


def _coerce_score(
    value: Any,
    *,
    metrics: dict[str, float | None],
    assessment: str | None,
) -> float:
    maybe_score = _coerce_float(value)
    if maybe_score is None:
        return _score_candidate(metrics=metrics, assessment=assessment)
    return round(max(0.0, min(maybe_score, 100.0)), 2)


def _resolve_metric(
    admet_properties: Mapping[str, float | str | bool | None],
    metric_name: str,
) -> float | None:
    direct = admet_properties.get(metric_name)
    direct_numeric = _coerce_float(direct)
    if direct_numeric is not None:
        return direct_numeric

    for key, value in admet_properties.items():
        if metric_name not in key.lower():
            continue
        numeric = _coerce_float(value)
        if numeric is not None:
            return numeric
    return None


def _resolve_text(
    admet_properties: Mapping[str, float | str | bool | None],
    label: str,
) -> str | None:
    direct = admet_properties.get(label)
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    for key, value in admet_properties.items():
        if label not in key.lower():
            continue
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _score_candidate(
    *, metrics: dict[str, float | None], assessment: str | None
) -> float:
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
    transformed = 1.0 / (1.0 + math.log10(value + 1.0))
    return _clamp01(transformed)


def _clamp01(value: float) -> float:
    if value < 0:
        return 0.0
    if value > 1:
        return 1.0
    return value


def _flatten(value: Any, prefix: str, out: dict[str, Any]) -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            next_prefix = f"{prefix}.{key}" if prefix else str(key)
            _flatten(nested, next_prefix, out)
        return
    if isinstance(value, list):
        for idx, nested in enumerate(value):
            next_prefix = f"{prefix}[{idx}]" if prefix else f"[{idx}]"
            _flatten(nested, next_prefix, out)
        return
    if _is_scalar(value):
        out[prefix] = value


def _is_scalar(value: Any) -> bool:
    return isinstance(value, (str, int, float, bool)) or value is None


def _pick_string(
    flat: dict[str, Any], aliases: list[str]
) -> tuple[str | None, str | None]:
    value, path = _pick_value(flat, aliases)
    if isinstance(value, str):
        cleaned = value.strip()
        if cleaned:
            return cleaned, path
    return None, None


def _pick_float(
    flat: dict[str, Any], aliases: list[str]
) -> tuple[float | None, str | None]:
    value, path = _pick_value(flat, aliases)
    return _coerce_float(value), path


def _coerce_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _optional_text(value: Any) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        if stripped:
            return stripped
    return None


def _pick_value(
    flat: dict[str, Any], aliases: list[str]
) -> tuple[Any | None, str | None]:
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
