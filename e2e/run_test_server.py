from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

from clawcures_ui.storage import JobStore


def _seed_job(
    store: JobStore,
    *,
    kind: str,
    objective: str,
    promising_cures: list[dict[str, object]],
) -> None:
    job = store.create_job(kind=kind, request={"objective": objective})
    store.set_running(job["job_id"])
    store.set_completed(
        job["job_id"],
        {
            "objective": objective,
            "promising_cures": promising_cures,
        },
    )


def _seed_fixture(data_dir: Path) -> None:
    shutil.rmtree(data_dir, ignore_errors=True)
    data_dir.mkdir(parents=True, exist_ok=True)
    store = JobStore(data_dir / "studio.db")

    _seed_job(
        store,
        kind="campaign_run",
        objective="Prioritize KRAS G12D therapeutics",
        promising_cures=[
            {
                "cure_id": "drug:lumatrol",
                "name": "Lumatrol",
                "target": "KRAS G12D",
                "smiles": "CCN(CC)C1=CC=CC=C1",
                "tool": "refua_affinity",
                "score": 82.4,
                "promising": True,
                "assessment": "Strong binding signal with favorable ADMET.",
                "metrics": {
                    "binding_probability": 0.87,
                    "admet_score": 0.74,
                },
                "admet": {
                    "status": "favorable",
                    "key_metrics": {
                        "admet_score": 0.74,
                        "safety_score": 0.81,
                    },
                    "properties": {
                        "solubility": 0.61,
                        "caco2": 0.58,
                    },
                },
            },
            {
                "cure_id": "drug:heliomab",
                "name": "Heliomab",
                "target": "EGFR exon 20",
                "smiles": "NCCOC1=CC=CC=C1",
                "tool": "refua_affinity",
                "score": 56.2,
                "promising": False,
                "assessment": "Signal exists but potency still needs work.",
                "metrics": {
                    "binding_probability": 0.49,
                    "admet_score": 0.63,
                },
                "admet": {
                    "status": "mixed",
                    "key_metrics": {
                        "admet_score": 0.63,
                    },
                },
            },
        ],
    )

    _seed_job(
        store,
        kind="plan_execute",
        objective="Cross-check Lumatrol ADMET",
        promising_cures=[
            {
                "cure_id": "drug:lumatrol",
                "name": "Lumatrol",
                "target": "KRAS G12D",
                "smiles": "CCN(CC)C1=CC=CC=C1",
                "tool": "refua_admet_profile",
                "score": 84.1,
                "promising": True,
                "assessment": "ADMET profile remains favorable after cross-check.",
                "metrics": {
                    "binding_probability": 0.87,
                    "admet_score": 0.79,
                },
                "admet": {
                    "status": "favorable",
                    "key_metrics": {
                        "admet_score": 0.79,
                        "safety_score": 0.83,
                    },
                    "properties": {
                        "solubility": 0.64,
                        "caco2": 0.59,
                    },
                },
            }
        ],
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", required=True)
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--workspace-root", required=True)
    parser.add_argument("--max-workers", default="2")
    args = parser.parse_args()

    data_dir = Path(args.data_dir).resolve()
    _seed_fixture(data_dir)

    os.execv(
        sys.executable,
        [
            sys.executable,
            "-m",
            "clawcures_ui",
            "--host",
            args.host,
            "--port",
            args.port,
            "--data-dir",
            str(data_dir),
            "--workspace-root",
            str(Path(args.workspace_root).resolve()),
            "--max-workers",
            str(args.max_workers),
        ],
    )


if __name__ == "__main__":
    main()
