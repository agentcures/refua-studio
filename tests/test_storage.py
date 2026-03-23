from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from clawcures_ui.storage import JobStore


class JobStoreTest(unittest.TestCase):
    def test_list_promising_drugs_aggregates_completed_job_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JobStore(Path(tmp) / "studio.db")

            first = store.create_job(
                kind="campaign_run",
                request={"objective": "Prioritize KRAS G12D therapeutics"},
            )
            store.set_running(first["job_id"])
            store.set_completed(
                first["job_id"],
                {
                    "objective": "Prioritize KRAS G12D therapeutics",
                    "promising_cures": [
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
                                "key_metrics": {"admet_score": 0.74},
                                "properties": {"solubility": 0.61},
                            },
                            "tool_args": {"target": "KRAS G12D"},
                        },
                        {
                            "cure_id": "drug:heliomab",
                            "name": "Heliomab",
                            "target": "EGFR exon 20",
                            "tool": "refua_affinity",
                            "score": 56.2,
                            "promising": False,
                            "assessment": "Signal exists but potency needs more work.",
                            "metrics": {"binding_probability": 0.49},
                            "admet": {"status": "mixed"},
                        },
                    ],
                },
            )

            second = store.create_job(
                kind="plan_execute",
                request={"objective": "Cross-check Lumatrol ADMET"},
            )
            store.set_running(second["job_id"])
            store.set_completed(
                second["job_id"],
                {
                    "objective": "Cross-check Lumatrol ADMET",
                    "promising_cures": [
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
                                "properties": {"solubility": 0.64},
                            },
                            "tool_args": {"candidate": "Lumatrol"},
                        }
                    ],
                },
            )

            snapshot = store.list_promising_drugs(limit=20)

            self.assertEqual(snapshot["summary"]["total_drugs"], 2)
            self.assertEqual(snapshot["summary"]["promising_count"], 1)
            self.assertEqual(snapshot["summary"]["watchlist_count"], 1)
            self.assertEqual(snapshot["summary"]["source_jobs_count"], 2)
            self.assertEqual(snapshot["summary"]["total_observations"], 3)
            self.assertEqual(snapshot["facets"]["targets"], ["EGFR exon 20", "KRAS G12D"])
            self.assertEqual(
                snapshot["facets"]["tools"],
                ["refua_admet_profile", "refua_affinity"],
            )

            first_drug = snapshot["drugs"][0]
            self.assertEqual(first_drug["drug_id"], "drug:lumatrol")
            self.assertEqual(first_drug["name"], "Lumatrol")
            self.assertTrue(first_drug["promising"])
            self.assertEqual(first_drug["seen_count"], 2)
            self.assertEqual(first_drug["source_jobs_count"], 2)
            self.assertEqual(first_drug["promising_runs"], 2)
            self.assertEqual(
                first_drug["tools"],
                ["refua_admet_profile", "refua_affinity"],
            )
            self.assertEqual(first_drug["tool"], "refua_admet_profile")
            self.assertEqual(first_drug["metrics"]["admet_score"], 0.79)
            self.assertEqual(first_drug["sources"][0]["objective"], "Cross-check Lumatrol ADMET")

    def test_create_and_update_job(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JobStore(Path(tmp) / "studio.db")
            created = store.create_job(kind="campaign_run", request={"objective": "x"})

            self.assertEqual(created["status"], "queued")
            job_id = created["job_id"]

            store.set_running(job_id)
            running = store.get_job(job_id)
            self.assertIsNotNone(running)
            assert running is not None
            self.assertEqual(running["status"], "running")

            store.set_completed(job_id, {"ok": True})
            done = store.get_job(job_id)
            self.assertIsNotNone(done)
            assert done is not None
            self.assertEqual(done["status"], "completed")
            self.assertEqual(done["result"], {"ok": True})

    def test_list_jobs_descending(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JobStore(Path(tmp) / "studio.db")
            first = store.create_job(kind="a", request={"i": 1})
            second = store.create_job(kind="b", request={"i": 2})
            store.set_completed(first["job_id"], {"one": 1})
            store.set_running(second["job_id"])
            store.set_failed(second["job_id"], "boom")

            jobs = store.list_jobs(limit=10)
            self.assertEqual(len(jobs), 2)
            self.assertIn(jobs[0]["status"], {"failed", "completed"})

    def test_cancel_and_clear(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JobStore(Path(tmp) / "studio.db")
            queued = store.create_job(kind="queued", request={})
            done = store.create_job(kind="done", request={})
            store.set_running(done["job_id"])
            store.set_completed(done["job_id"], {"ok": 1})

            cancelled = store.set_cancelled(queued["job_id"], "by test")
            self.assertTrue(cancelled)
            queued_row = store.get_job(queued["job_id"])
            self.assertIsNotNone(queued_row)
            assert queued_row is not None
            self.assertEqual(queued_row["status"], "cancelled")

            deleted = store.clear_jobs(statuses=("completed", "cancelled"))
            self.assertEqual(deleted, 2)
            self.assertEqual(store.list_jobs(limit=10), [])


if __name__ == "__main__":
    unittest.main()
