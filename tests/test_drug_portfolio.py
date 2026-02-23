from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from refua_studio.drug_portfolio import build_drug_portfolio


class DrugPortfolioTest(unittest.TestCase):
    def test_extracts_candidate_from_tool_output(self) -> None:
        jobs = [
            {
                "job_id": "job-1",
                "kind": "campaign_run",
                "status": "completed",
                "updated_at": "2026-02-16T00:00:00+00:00",
                "request": {"objective": "test objective"},
                "result": {
                    "results": [
                        {
                            "tool": "refua_fold",
                            "args": {
                                "name": "candidate_a",
                                "entities": [{"type": "ligand", "smiles": "CCO"}],
                            },
                            "output": {
                                "target": "KRAS",
                                "affinity": {
                                    "binding_probability": 0.84,
                                    "ic50": 0.11,
                                },
                                "admet_score": 0.71,
                                "assessment": "promising profile",
                            },
                        }
                    ]
                },
            }
        ]

        payload = build_drug_portfolio(jobs, min_score=0.0, limit=50, include_raw=False)
        self.assertEqual(payload["summary"]["total_candidates"], 1)
        self.assertEqual(len(payload["candidates"]), 1)

        candidate = payload["candidates"][0]
        self.assertEqual(candidate["target"], "KRAS")
        self.assertEqual(candidate["smiles"], "CCO")
        self.assertGreater(candidate["score"], 50)
        self.assertEqual(candidate["source"]["objective"], "test objective")
        self.assertIn("admet", candidate)

    def test_prefers_clawcures_promising_cure_payload(self) -> None:
        jobs = [
            {
                "job_id": "job-2",
                "kind": "campaign_run",
                "status": "completed",
                "updated_at": "2026-02-16T00:00:00+00:00",
                "request": {"objective": "test objective"},
                "result": {
                    "promising_cures": [
                        {
                            "cure_id": "refua_fold:kras-alpha",
                            "name": "KRAS Alpha",
                            "smiles": "CCN",
                            "target": "KRAS",
                            "tool": "refua_fold",
                            "score": 88.1,
                            "promising": True,
                            "assessment": "promising safety profile",
                            "metrics": {
                                "binding_probability": 0.89,
                                "admet_score": 0.84,
                            },
                            "admet": {
                                "status": "success",
                                "key_metrics": {
                                    "admet_score": 0.84,
                                    "safety_score": 0.9,
                                },
                                "properties": {
                                    "results[0].predictions.hERG": 0.11,
                                    "results[0].predictions.AMES": 0.07,
                                },
                            },
                        }
                    ]
                },
            }
        ]

        payload = build_drug_portfolio(jobs, min_score=0.0, limit=20, include_raw=False)
        self.assertEqual(payload["summary"]["returned_candidates"], 1)
        self.assertEqual(payload["summary"]["with_admet_properties"], 1)
        candidate = payload["candidates"][0]
        self.assertEqual(candidate["candidate_id"], "refua_fold:kras-alpha")
        self.assertEqual(candidate["admet"]["status"], "success")
        self.assertIn("results[0].predictions.hERG", candidate["admet"]["properties"])


if __name__ == "__main__":
    unittest.main()
