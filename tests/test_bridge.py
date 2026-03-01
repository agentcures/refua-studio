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

    def test_command_center_capabilities(self) -> None:
        payload = self.bridge.command_center_capabilities()
        self.assertIn("integrations", payload)
        self.assertGreaterEqual(len(payload["integrations"]), 1)

    def test_wetlab_protocol_validation(self) -> None:
        payload = self.bridge.wetlab_validate_protocol(
            protocol={
                "name": "bridge-wetlab",
                "steps": [
                    {
                        "type": "transfer",
                        "source": "plate:A1",
                        "destination": "plate:B1",
                        "volume_ul": 20,
                    }
                ],
            }
        )
        self.assertTrue(payload["valid"])

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

                site = self.bridge.upsert_clinical_site(
                    trial_id="bridge-clinical",
                    site_id="site-001",
                    name="Boston General",
                    country_id="US",
                    status="active",
                    principal_investigator="Dr. Rivera",
                    target_enrollment=20,
                    metadata={},
                )
                self.assertEqual(site["site"]["site_id"], "site-001")

                enrolled = self.bridge.enroll_clinical_patient(
                    trial_id="bridge-clinical",
                    patient_id="human-001",
                    source="human",
                    arm_id="control",
                    site_id="site-001",
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
                    site_id="site-001",
                )
                self.assertIn("result", result)

                _ = self.bridge.record_clinical_screening(
                    trial_id="bridge-clinical",
                    site_id="site-001",
                    patient_id="screen-001",
                    status="screen_failed",
                    arm_id=None,
                    source="human",
                    failure_reason="criteria",
                    demographics=None,
                    baseline=None,
                    metadata=None,
                    auto_enroll=False,
                )
                _ = self.bridge.record_clinical_monitoring_visit(
                    trial_id="bridge-clinical",
                    site_id="site-001",
                    visit_type="interim",
                    findings=["missing source signatures"],
                    action_items=["retrain coordinator"],
                    risk_score=0.8,
                    outcome=None,
                    metadata=None,
                )
                query = self.bridge.add_clinical_query(
                    trial_id="bridge-clinical",
                    patient_id="human-001",
                    site_id="site-001",
                    field_name="ecg_date",
                    description="Missing baseline ECG",
                    status="open",
                    severity="major",
                    assignee=None,
                    due_at="2000-01-01T00:00:00+00:00",
                    metadata=None,
                )
                self.assertIn("query", query)
                query_id = query["query"]["query_id"]
                _ = self.bridge.update_clinical_query(
                    trial_id="bridge-clinical",
                    query_id=query_id,
                    updates={"status": "resolved", "resolution": "ECG uploaded"},
                )
                _ = self.bridge.add_clinical_deviation(
                    trial_id="bridge-clinical",
                    description="Visit window deviation",
                    site_id="site-001",
                    patient_id="human-001",
                    category="protocol",
                    severity="major",
                    status="open",
                    corrective_action=None,
                    preventive_action=None,
                    metadata=None,
                )
                _ = self.bridge.add_clinical_safety_event(
                    trial_id="bridge-clinical",
                    patient_id="human-001",
                    event_term="grade_3_neutropenia",
                    site_id="site-001",
                    seriousness="serious",
                    expected=False,
                    relatedness="possible",
                    outcome="recovering",
                    action_taken="dose_hold",
                    metadata=None,
                )
                _ = self.bridge.upsert_clinical_milestone(
                    trial_id="bridge-clinical",
                    milestone_id="ms-lpi",
                    name="Last Patient In",
                    target_date="2000-01-01T00:00:00+00:00",
                    status="at_risk",
                    owner=None,
                    actual_date=None,
                    metadata=None,
                )
                sites = self.bridge.list_clinical_sites(trial_id="bridge-clinical")
                self.assertGreaterEqual(sites["count"], 1)
                ops = self.bridge.clinical_ops_snapshot(trial_id="bridge-clinical")
                self.assertGreaterEqual(ops["clinops"]["site_count"], 1)

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
