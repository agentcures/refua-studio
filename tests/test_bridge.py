from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from refua_studio.bridge import CampaignBridge


class CampaignBridgeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace_root = Path(__file__).resolve().parents[2]
        self.bridge = CampaignBridge(self.workspace_root)

    def test_available_tools_has_known_entries(self) -> None:
        tools, _warnings = self.bridge.available_tools()
        self.assertIn("refua_validate_spec", tools)
        self.assertIn("refua_protein_properties", tools)
        self.assertIn("refua_data_list", tools)

    def test_validate_plan(self) -> None:
        payload = self.bridge.validate_plan(
            plan={
                "calls": [
                    {"tool": "refua_validate_spec", "args": {}},
                ]
            },
            max_calls=10,
            allow_skip_validate_first=False,
        )
        self.assertTrue(payload["approved"])
        self.assertEqual(payload["errors"], [])

    def test_rank_portfolio(self) -> None:
        payload = self.bridge.rank_portfolio(
            programs=[
                {"name": "A", "burden": 0.9, "tractability": 0.2, "unmet_need": 0.9},
                {"name": "B", "burden": 0.7, "tractability": 0.9, "unmet_need": 0.7},
            ],
            weights=None,
        )
        self.assertIn("ranked", payload)
        self.assertEqual(len(payload["ranked"]), 2)

    def test_examples_payload(self) -> None:
        payload = self.bridge.examples()
        self.assertIn("objectives", payload)
        self.assertIn("plan_templates", payload)
        self.assertGreaterEqual(len(payload["objectives"]), 1)

    def test_ecosystem_payload(self) -> None:
        payload = self.bridge.ecosystem()
        self.assertIn("products", payload)
        self.assertIn("clawcures", payload)
        self.assertIsInstance(payload["products"], list)
        self.assertGreaterEqual(len(payload["products"]), 1)
        self.assertIn("default_objective", payload["clawcures"])

    def test_build_clawcures_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = self.bridge.build_clawcures_handoff(
                objective="Bridge handoff test",
                plan={"calls": [{"tool": "refua_validate_spec", "args": {}}]},
                system_prompt=None,
                autonomous=False,
                dry_run=True,
                max_calls=10,
                allow_skip_validate_first=False,
                write_file=True,
                artifact_dir=Path(tmp),
                artifact_name="bridge_test_handoff.json",
            )
            self.assertIn("artifact", payload)
            self.assertIn("commands", payload)
            self.assertIsNotNone(payload["artifact_path"])
            assert payload["artifact_path"] is not None
            self.assertTrue(Path(payload["artifact_path"]).exists())

    def test_clinical_trial_bridge_flow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            previous = os.environ.get("REFUA_CLINICAL_TRIAL_STORE")
            os.environ["REFUA_CLINICAL_TRIAL_STORE"] = str(Path(tmp) / "clinical_trials.json")
            try:
                created = self.bridge.add_clinical_trial(
                    trial_id="bridge-clinical",
                    config=None,
                    indication="Oncology",
                    phase="Phase II",
                    objective="Bridge clinical flow",
                    status="planned",
                    metadata=None,
                )
                self.assertEqual(created["trial"]["trial_id"], "bridge-clinical")

                listing = self.bridge.list_clinical_trials()
                self.assertGreaterEqual(listing["count"], 1)

                enrolled = self.bridge.enroll_clinical_patient(
                    trial_id="bridge-clinical",
                    patient_id="human-001",
                    source="human",
                    arm_id="control",
                    demographics={"age": 60},
                    baseline={"endpoint_value": 50.0},
                    metadata={},
                )
                self.assertEqual(enrolled["patient"]["patient_id"], "human-001")

                result = self.bridge.add_clinical_result(
                    trial_id="bridge-clinical",
                    patient_id="human-001",
                    values={
                        "arm_id": "control",
                        "change": 4.2,
                        "responder": False,
                        "safety_event": False,
                    },
                    result_type="endpoint",
                    visit="week-12",
                    source="human",
                )
                self.assertIn("result", result)

                simulated = self.bridge.simulate_clinical_trial(
                    trial_id="bridge-clinical",
                    replicates=3,
                    seed=7,
                )
                self.assertIn("simulation", simulated)
            finally:
                if previous is None:
                    os.environ.pop("REFUA_CLINICAL_TRIAL_STORE", None)
                else:
                    os.environ["REFUA_CLINICAL_TRIAL_STORE"] = previous


if __name__ == "__main__":
    unittest.main()
