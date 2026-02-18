from __future__ import annotations

import json
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

    def test_examples_endpoint(self) -> None:
        payload = self._request("GET", "/api/examples")
        self.assertIn("objectives", payload)
        self.assertIn("plan_templates", payload)

    def test_drug_portfolio_endpoint(self) -> None:
        job = self.app.store.create_job(kind="candidate-run", request={"objective": "find drugs"})
        self.app.store.set_running(job["job_id"])
        self.app.store.set_completed(
            job["job_id"],
            {
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
