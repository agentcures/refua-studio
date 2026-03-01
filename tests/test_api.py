from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from refua_studio.app import create_server
from refua_studio.config import StudioConfig


class StudioApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._prev_trial_store = os.environ.get("REFUA_CLINICAL_TRIAL_STORE")
        os.environ["REFUA_CLINICAL_TRIAL_STORE"] = str(
            Path(self._tmp.name) / "data" / "clinical_trials.json"
        )
        config = StudioConfig(
            host="127.0.0.1",
            port=0,
            data_dir=Path(self._tmp.name) / "data",
            workspace_root=Path(__file__).resolve().parents[2],
            max_workers=1,
        )
        self.server, self.app = create_server(config)
        self.host, self.port = self.server.server_address
        self._thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self._thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.app.shutdown()
        self._thread.join(timeout=2)
        if self._prev_trial_store is None:
            os.environ.pop("REFUA_CLINICAL_TRIAL_STORE", None)
        else:
            os.environ["REFUA_CLINICAL_TRIAL_STORE"] = self._prev_trial_store
        self._tmp.cleanup()

    def _request(self, method: str, path: str, payload: dict | None = None) -> dict:
        url = f"http://{self.host}:{self.port}{path}"
        data = None
        headers = {}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = Request(url, method=method, data=data, headers=headers)
        try:
            with urlopen(request, timeout=5) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            body = exc.read().decode("utf-8")
            raise AssertionError(f"HTTP {exc.code} for {path}: {body}") from exc

    def test_health_and_tools(self) -> None:
        health = self._request("GET", "/api/health")
        self.assertTrue(health["ok"])

        tools = self._request("GET", "/api/tools")
        self.assertIn("tools", tools)
        self.assertIn("refua_validate_spec", tools["tools"])
        self.assertIn("refua_protein_properties", tools["tools"])
        self.assertIn("refua_data_list", tools["tools"])

    def test_examples_endpoint(self) -> None:
        payload = self._request("GET", "/api/examples")
        self.assertIn("objectives", payload)
        self.assertIn("plan_templates", payload)

    def test_ecosystem_endpoint(self) -> None:
        payload = self._request("GET", "/api/ecosystem")
        self.assertIn("products", payload)
        self.assertIn("clawcures", payload)
        self.assertIsInstance(payload["products"], list)
        self.assertGreaterEqual(len(payload["products"]), 1)
        self.assertIn("default_objective", payload["clawcures"])
        names = {item.get("name") for item in payload["products"]}
        self.assertIn("refua-preclinical", names)

    def test_command_center_capabilities_endpoint(self) -> None:
        payload = self._request("GET", "/api/command-center/capabilities")
        self.assertIn("integrations", payload)
        self.assertGreaterEqual(len(payload["integrations"]), 1)

    def test_clawcures_handoff_endpoint(self) -> None:
        payload = self._request(
            "POST",
            "/api/clawcures/handoff",
            {
                "objective": "Offline handoff generation",
                "plan": {
                    "calls": [
                        {"tool": "refua_validate_spec", "args": {}},
                    ]
                },
                "write_file": False,
            },
        )
        self.assertIn("artifact", payload)
        self.assertIn("commands", payload)
        self.assertIsNone(payload["artifact_path"])
        self.assertGreaterEqual(len(payload["commands"]), 1)

    def test_drug_portfolio_endpoint(self) -> None:
        job = self.app.store.create_job(kind="candidate-run", request={"objective": "find drugs"})
        self.app.store.set_running(job["job_id"])
        self.app.store.set_completed(
            job["job_id"],
            {
                "promising_cures": [
                    {
                        "cure_id": "refua_fold:candidate_x",
                        "name": "candidate_x",
                        "smiles": "CCN",
                        "target": "EGFR",
                        "tool": "refua_fold",
                        "score": 84.0,
                        "promising": True,
                        "assessment": "promising profile",
                        "metrics": {
                            "binding_probability": 0.9,
                            "admet_score": 0.8,
                        },
                        "admet": {
                            "status": "success",
                            "key_metrics": {"admet_score": 0.8},
                            "properties": {"results[0].predictions.hERG": 0.12},
                        },
                    }
                ],
                "results": [
                    {
                        "tool": "refua_fold",
                        "args": {"name": "candidate_x", "smiles": "CCN"},
                        "output": {
                            "target": "EGFR",
                            "binding_probability": 0.9,
                            "admet_score": 0.8,
                            "assessment": "promising",
                        },
                    }
                ]
            },
        )

        payload = self._request("GET", "/api/drug-portfolio?min_score=0&limit=20")
        self.assertIn("summary", payload)
        self.assertIn("candidates", payload)
        self.assertGreaterEqual(payload["summary"]["returned_candidates"], 1)
        self.assertGreaterEqual(payload["summary"]["with_admet_properties"], 1)
        self.assertIn("admet", payload["candidates"][0])

        alias_payload = self._request("GET", "/api/promising-cures?min_score=0&limit=20")
        self.assertIn("summary", alias_payload)
        self.assertIn("candidates", alias_payload)

    def test_program_graph_endpoints(self) -> None:
        upserted = self._request(
            "POST",
            "/api/programs/upsert",
            {
                "program_id": "kras-program",
                "name": "KRAS Program",
                "stage": "hit_to_lead",
                "owner": "team-a",
            },
        )
        self.assertEqual(upserted["program"]["program_id"], "kras-program")

        _ = self._request(
            "POST",
            "/api/programs/kras-program/events/add",
            {
                "event_type": "campaign_run",
                "title": "Run submitted",
                "status": "queued",
                "payload": {"objective": "test"},
            },
        )
        approval = self._request(
            "POST",
            "/api/programs/kras-program/approve",
            {
                "gate": "stage_gate",
                "decision": "approved",
                "signer": "user-1",
                "signature": "sig-1",
            },
        )
        self.assertEqual(approval["approval"]["decision"], "approved")

        detail = self._request("GET", "/api/programs/kras-program")
        self.assertEqual(detail["program"]["program_id"], "kras-program")
        self.assertGreaterEqual(len(detail["events"]), 1)
        self.assertGreaterEqual(len(detail["approvals"]), 1)

    def test_stage_gate_and_job_sync_endpoints(self) -> None:
        _ = self._request(
            "POST",
            "/api/programs/upsert",
            {
                "program_id": "sync-program",
                "name": "Sync Program",
                "owner": "team-sync",
            },
        )

        templates = self._request("GET", "/api/program-gates/templates")
        self.assertGreaterEqual(templates["count"], 1)

        gate = self._request(
            "POST",
            "/api/programs/sync-program/gate-evaluate",
            {
                "template_id": "hit_to_lead",
                "metrics": {
                    "promising_leads": 4,
                    "mean_admet_score": 0.7,
                    "mean_binding_probability": 0.81,
                },
                "auto_record": True,
            },
        )
        self.assertIn("evaluation", gate)
        self.assertTrue(gate["evaluation"]["passed"])

        run_payload = self._request(
            "POST",
            "/api/run",
            {
                "objective": "Sync jobs test",
                "dry_run": True,
                "async_mode": True,
                "program_id": "sync-program",
                "plan": {
                    "calls": [
                        {"tool": "refua_validate_spec", "args": {}},
                    ]
                },
            },
        )
        self.assertIn("job", run_payload)
        job_id = run_payload["job"]["job_id"]

        deadline = time.time() + 5
        while time.time() < deadline:
            current = self._request("GET", f"/api/jobs/{job_id}")
            if current["status"] in {"completed", "failed", "cancelled"}:
                break
            time.sleep(0.1)

        synced = self._request(
            "POST",
            "/api/programs/sync-jobs",
            {"limit": 100},
        )
        self.assertIn("linked_events", synced)

        detail = self._request("GET", "/api/programs/sync-program")
        self.assertGreaterEqual(len(detail["events"]), 1)

    def test_data_wetlab_and_benchmark_endpoints(self) -> None:
        data_payload = self._request("GET", "/api/data/datasets?limit=5")
        self.assertGreaterEqual(data_payload["count"], 1)

        wetlab_validate = self._request(
            "POST",
            "/api/wetlab/protocol/validate",
            {
                "protocol": {
                    "name": "api-test",
                    "steps": [
                        {
                            "type": "transfer",
                            "source": "plate:A1",
                            "destination": "plate:B1",
                            "volume_ul": 20,
                        }
                    ],
                }
            },
        )
        self.assertTrue(wetlab_validate["valid"])

        benchmark = self._request(
            "POST",
            "/api/bench/gate",
            {
                "suite_path": "refua-bench/benchmarks/sample_suite.yaml",
                "baseline_run_path": "refua-bench/benchmarks/sample_baseline_run.json",
                "adapter_spec": "file",
                "adapter_config": {
                    "predictions_path": "refua-bench/benchmarks/sample_predictions_candidate.json",
                },
                "async_mode": False,
            },
        )
        self.assertIn("result", benchmark)
        self.assertIn("comparison", benchmark["result"])

    def test_regulatory_bundle_endpoints(self) -> None:
        payload = self._request(
            "POST",
            "/api/regulatory/bundle/build",
            {
                "campaign_run": {
                    "objective": "regulatory test",
                    "plan": {
                        "calls": [
                            {"tool": "refua_validate_spec", "args": {}},
                        ]
                    },
                    "results": [
                        {
                            "tool": "refua_validate_spec",
                            "args": {},
                            "output": {"valid": True},
                        }
                    ],
                },
                "async_mode": False,
                "overwrite": True,
            },
        )
        self.assertIn("result", payload)
        bundle_dir = payload["result"]["bundle_dir"]
        verify = self._request(
            "POST",
            "/api/regulatory/bundle/verify",
            {"bundle_dir": bundle_dir},
        )
        self.assertIn("result", verify)
        self.assertIn("verification", verify["result"])

    def test_validate_plan_endpoint(self) -> None:
        payload = self._request(
            "POST",
            "/api/plan/validate",
            {
                "plan": {
                    "calls": [
                        {"tool": "refua_validate_spec", "args": {}},
                    ]
                },
                "max_calls": 5,
            },
        )
        self.assertTrue(payload["approved"])

    def test_portfolio_rank_endpoint(self) -> None:
        payload = self._request(
            "POST",
            "/api/portfolio/rank",
            {
                "programs": [
                    {
                        "name": "Pancreatic cancer",
                        "burden": 0.92,
                        "tractability": 0.45,
                        "unmet_need": 0.95,
                    },
                    {
                        "name": "Tuberculosis",
                        "burden": 0.88,
                        "tractability": 0.68,
                        "unmet_need": 0.90,
                    },
                ]
            },
        )
        self.assertEqual(len(payload["ranked"]), 2)

    def test_clinical_trial_management_endpoints(self) -> None:
        created = self._request(
            "POST",
            "/api/clinical/trials/add",
            {
                "trial_id": "studio-clinical",
                "indication": "Oncology",
                "phase": "Phase II",
                "objective": "Manage adaptive trial operations",
                "status": "planned",
            },
        )
        self.assertIn("trial", created)
        self.assertEqual(created["trial"]["trial_id"], "studio-clinical")

        listing = self._request("GET", "/api/clinical/trials")
        self.assertGreaterEqual(listing["count"], 1)
        trial_ids = [item["trial_id"] for item in listing["trials"]]
        self.assertIn("studio-clinical", trial_ids)

        detail = self._request("GET", "/api/clinical/trials/studio-clinical")
        self.assertIn("trial", detail)
        self.assertEqual(detail["trial"]["trial_id"], "studio-clinical")

        site = self._request(
            "POST",
            "/api/clinical/trials/site/upsert",
            {
                "trial_id": "studio-clinical",
                "site_id": "site-001",
                "name": "Boston General",
                "country_id": "US",
                "status": "active",
                "target_enrollment": 30,
            },
        )
        self.assertIn("site", site)
        self.assertEqual(site["site"]["site_id"], "site-001")

        screening = self._request(
            "POST",
            "/api/clinical/trials/screen",
            {
                "trial_id": "studio-clinical",
                "site_id": "site-001",
                "patient_id": "screen-001",
                "status": "screen_failed",
                "failure_reason": "inclusion_criteria_not_met",
            },
        )
        self.assertIn("screening", screening)

        _ = self._request(
            "POST",
            "/api/clinical/trials/update",
            {
                "trial_id": "studio-clinical",
                "updates": {
                    "status": "active",
                    "config": {
                        "replicates": 6,
                        "enrollment": {"total_n": 60},
                        "adaptive": {"burn_in_n": 20, "interim_every": 20},
                    },
                },
            },
        )

        enrolled = self._request(
            "POST",
            "/api/clinical/trials/enroll",
            {
                "trial_id": "studio-clinical",
                "patient_id": "human-001",
                "source": "human",
                "arm_id": "control",
                "site_id": "site-001",
                "demographics": {"age": 62},
            },
        )
        self.assertIn("patient", enrolled)
        self.assertEqual(enrolled["patient"]["patient_id"], "human-001")

        _ = self._request(
            "POST",
            "/api/clinical/trials/result",
            {
                "trial_id": "studio-clinical",
                "patient_id": "human-001",
                "site_id": "site-001",
                "values": {
                    "arm_id": "control",
                    "change": 4.4,
                    "responder": False,
                    "safety_event": False,
                },
            },
        )

        monitoring = self._request(
            "POST",
            "/api/clinical/trials/monitoring/visit",
            {
                "trial_id": "studio-clinical",
                "site_id": "site-001",
                "visit_type": "interim",
                "findings": ["missing source signatures"],
                "action_items": ["retrain study coordinator"],
                "risk_score": 0.8,
            },
        )
        self.assertIn("monitoring_visit", monitoring)

        query_added = self._request(
            "POST",
            "/api/clinical/trials/query/add",
            {
                "trial_id": "studio-clinical",
                "site_id": "site-001",
                "patient_id": "human-001",
                "description": "Missing baseline ECG",
                "status": "open",
                "due_at": "2000-01-01T00:00:00+00:00",
            },
        )
        self.assertIn("query", query_added)
        query_id = query_added["query"]["query_id"]

        query_updated = self._request(
            "POST",
            "/api/clinical/trials/query/update",
            {
                "trial_id": "studio-clinical",
                "query_id": query_id,
                "updates": {"status": "resolved", "resolution": "uploaded ECG source"},
            },
        )
        self.assertEqual(query_updated["query"]["status"], "resolved")

        deviation = self._request(
            "POST",
            "/api/clinical/trials/deviation/add",
            {
                "trial_id": "studio-clinical",
                "site_id": "site-001",
                "patient_id": "human-001",
                "description": "Visit outside protocol window",
                "severity": "major",
            },
        )
        self.assertIn("deviation", deviation)

        safety = self._request(
            "POST",
            "/api/clinical/trials/safety/add",
            {
                "trial_id": "studio-clinical",
                "site_id": "site-001",
                "patient_id": "human-001",
                "event_term": "grade_3_neutropenia",
                "seriousness": "serious",
                "expected": False,
            },
        )
        self.assertIn("safety_event", safety)

        milestone = self._request(
            "POST",
            "/api/clinical/trials/milestone/upsert",
            {
                "trial_id": "studio-clinical",
                "milestone_id": "ms-lpi",
                "name": "Last Patient In",
                "target_date": "2000-01-01T00:00:00+00:00",
                "status": "at_risk",
            },
        )
        self.assertIn("milestone", milestone)

        sites = self._request("GET", "/api/clinical/trials/studio-clinical/sites")
        self.assertGreaterEqual(sites["count"], 1)
        self.assertEqual(sites["sites"][0]["site_id"], "site-001")

        ops = self._request("GET", "/api/clinical/trials/studio-clinical/ops")
        self.assertIn("clinops", ops)
        self.assertGreaterEqual(ops["clinops"]["site_count"], 1)

        simulated = self._request(
            "POST",
            "/api/clinical/trials/simulate",
            {
                "trial_id": "studio-clinical",
                "replicates": 3,
                "seed": 7,
                "async_mode": False,
            },
        )
        self.assertIn("result", simulated)
        summary = simulated["result"]["simulation"]["summary"]
        self.assertIn("blended_effect_estimate", summary)

    def test_preclinical_endpoints(self) -> None:
        templates = self._request("GET", "/api/preclinical/templates")
        self.assertIn("templates", templates)
        self.assertIn("study", templates["templates"])
        self.assertIn("references", templates)
        self.assertGreaterEqual(len(templates["references"]), 1)

        study = templates["templates"]["study"]
        rows = templates["templates"]["bioanalysis_rows"]

        plan = self._request(
            "POST",
            "/api/preclinical/plan",
            {"study": study, "seed": 11},
        )
        self.assertIn("plan", plan)
        self.assertEqual(plan["plan"]["study_id"], study["study_id"])

        schedule = self._request(
            "POST",
            "/api/preclinical/schedule",
            {"study": study},
        )
        self.assertIn("schedule", schedule)
        self.assertGreater(schedule["schedule"]["event_count"], 0)

        bio = self._request(
            "POST",
            "/api/preclinical/bioanalysis",
            {"study": study, "rows": rows, "lloq_ng_ml": 1.0},
        )
        self.assertIn("bioanalysis", bio)
        self.assertGreaterEqual(bio["bioanalysis"]["parsed_rows"], 1)

        workup = self._request(
            "POST",
            "/api/preclinical/workup",
            {"study": study, "rows": rows, "seed": 7, "lloq_ng_ml": 1.0},
        )
        self.assertIn("workup", workup)
        self.assertIn("plan", workup["workup"])

    def test_async_run_job(self) -> None:
        run_payload = self._request(
            "POST",
            "/api/run",
            {
                "objective": "Offline dry-run validation",
                "dry_run": True,
                "async_mode": True,
                "plan": {
                    "calls": [
                        {"tool": "refua_validate_spec", "args": {}},
                    ]
                },
            },
        )
        self.assertIn("job", run_payload)
        job_id = run_payload["job"]["job_id"]

        deadline = time.time() + 5
        last_status = "queued"
        while time.time() < deadline:
            job = self._request("GET", f"/api/jobs/{job_id}")
            last_status = job["status"]
            if last_status in {"completed", "failed"}:
                break
            time.sleep(0.1)

        self.assertIn(last_status, {"completed", "failed"})

    def test_cancel_queued_job(self) -> None:
        started = threading.Event()
        release = threading.Event()

        def _blocking() -> dict:
            started.set()
            release.wait(timeout=5)
            return {"ok": True}

        first_job = self.app.runner.submit(kind="blocking", request={}, fn=_blocking)
        self.assertTrue(started.wait(timeout=2))

        second_job = self.app.runner.submit(
            kind="queued",
            request={},
            fn=lambda: {"ok": True},
        )

        cancel_payload = self._request(
            "POST",
            f"/api/jobs/{second_job['job_id']}/cancel",
            {},
        )
        self.assertTrue(cancel_payload["cancelled"])
        self.assertEqual(cancel_payload["status"], "cancelled")

        second_status = self._request("GET", f"/api/jobs/{second_job['job_id']}")
        self.assertEqual(second_status["status"], "cancelled")

        release.set()
        deadline = time.time() + 5
        while time.time() < deadline:
            current = self._request("GET", f"/api/jobs/{first_job['job_id']}")
            if current["status"] in {"completed", "failed"}:
                break
            time.sleep(0.05)

    def test_clear_jobs_endpoint(self) -> None:
        completed = self.app.store.create_job(kind="completed-job", request={})
        failed = self.app.store.create_job(kind="failed-job", request={})
        self.app.store.set_running(completed["job_id"])
        self.app.store.set_completed(completed["job_id"], {"x": 1})
        self.app.store.set_running(failed["job_id"])
        self.app.store.set_failed(failed["job_id"], "boom")

        clear_payload = self._request(
            "POST",
            "/api/jobs/clear",
            {"statuses": ["completed", "failed"]},
        )
        self.assertGreaterEqual(clear_payload["deleted"], 2)

        jobs_payload = self._request("GET", "/api/jobs?status=completed,failed")
        self.assertEqual(jobs_payload["jobs"], [])

    def test_unknown_job_returns_404(self) -> None:
        url = f"http://{self.host}:{self.port}/api/jobs/not-a-real-job"
        request = Request(url, method="GET")
        with self.assertRaises(HTTPError) as ctx:
            urlopen(request, timeout=5)
        error = ctx.exception
        self.assertEqual(error.code, 404)
        _ = error.read()
        error.close()


if __name__ == "__main__":
    unittest.main()
