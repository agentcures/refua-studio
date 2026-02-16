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


if __name__ == "__main__":
    unittest.main()
