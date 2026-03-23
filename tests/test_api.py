from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from urllib.parse import quote
from unittest import mock
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from clawcures_ui.app import create_server
from clawcures_ui.config import StudioConfig


class StudioApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        config = StudioConfig(
            host="127.0.0.1",
            port=0,
            data_dir=Path(self._tmp.name) / "data",
            workspace_root=Path(__file__).resolve().parents[2],
            max_workers=1,
            autostart_agent=False,
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

    def _request(
        self,
        method: str,
        path: str,
        payload: dict | None = None,
        *,
        allow_error: bool = False,
        token: str | None = None,
    ) -> dict:
        url = f"http://{self.host}:{self.port}{path}"
        data = None
        headers = {}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if token:
            headers["Authorization"] = f"Bearer {token}"

        request = Request(url, method=method, data=data, headers=headers)
        try:
            with urlopen(request, timeout=5) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            body = exc.read().decode("utf-8")
            parsed = json.loads(body) if body else {}
            exc.close()
            if allow_error:
                return {"status_code": exc.code, "body": parsed}
            raise AssertionError(f"HTTP {exc.code} for {path}: {body}") from exc

    def _request_text(self, path: str) -> tuple[int, str, str]:
        url = f"http://{self.host}:{self.port}{path}"
        request = Request(url, method="GET")
        with urlopen(request, timeout=5) as response:
            return (
                response.status,
                response.headers.get_content_type(),
                response.read().decode("utf-8"),
            )

    def test_health_examples_and_ecosystem_endpoints(self) -> None:
        health = self._request("GET", "/api/health")
        self.assertTrue(health["ok"])
        self.assertIn("tools_count", health)
        self.assertIn("job_counts", health)

        examples = self._request("GET", "/api/examples")
        self.assertIn("objectives", examples)
        self.assertGreaterEqual(len(examples["objectives"]), 1)

        ecosystem = self._request("GET", "/api/ecosystem")
        self.assertIn("products", ecosystem)
        self.assertIn("clawcures", ecosystem)
        self.assertIn("default_objective", ecosystem["clawcures"])

    def test_removed_ui_endpoints_return_404(self) -> None:
        removed_gets = [
            "/api/tools",
            "/api/config",
            "/api/command-center/capabilities",
            "/api/drug-portfolio",
            "/api/clinical/trials",
            "/api/preclinical/templates",
        ]
        for path in removed_gets:
            payload = self._request("GET", path, allow_error=True)
            self.assertEqual(payload["status_code"], 404, path)

        removed_posts = [
            "/api/clawcures/handoff",
            "/api/portfolio/rank",
            "/api/programs/upsert",
            "/api/regulatory/bundle/build",
        ]
        for path in removed_posts:
            payload = self._request("POST", path, {}, allow_error=True)
            self.assertEqual(payload["status_code"], 404, path)

    def test_static_ui_routes(self) -> None:
        status, content_type, body = self._request_text("/")
        self.assertEqual(status, 200)
        self.assertEqual(content_type, "text/html")
        self.assertIn("ClawCures UI", body)

        status, content_type, body = self._request_text("/assets/app.js")
        self.assertEqual(status, 200)
        self.assertEqual(content_type, "application/javascript")
        self.assertIn("refreshJobs", body)
        self.assertIn("refreshPromisingDrugs", body)

    def test_promising_drugs_endpoint(self) -> None:
        first = self.app.store.create_job(
            kind="campaign_run",
            request={"objective": "Prioritize KRAS G12D therapeutics"},
        )
        self.app.store.set_running(first["job_id"])
        self.app.store.set_completed(
            first["job_id"],
            {
                "objective": "Prioritize KRAS G12D therapeutics",
                "promising_cures": [
                    {
                        "cure_id": "drug:lumotril",
                        "name": "Lumotril",
                        "target": "KRAS G12D",
                        "smiles": "CCOC1=CC=CC=C1",
                        "tool": "refua_affinity",
                        "score": 81.6,
                        "promising": True,
                        "assessment": "Strong binding and tractable chemistry.",
                        "metrics": {"binding_probability": 0.84, "admet_score": 0.72},
                        "admet": {
                            "status": "favorable",
                            "key_metrics": {"admet_score": 0.72},
                        },
                    }
                ],
            },
        )

        second = self.app.store.create_job(
            kind="plan_execute",
            request={"objective": "Cross-check Lumotril ADMET"},
        )
        self.app.store.set_running(second["job_id"])
        self.app.store.set_completed(
            second["job_id"],
            {
                "objective": "Cross-check Lumotril ADMET",
                "promising_cures": [
                    {
                        "cure_id": "drug:lumotril",
                        "name": "Lumotril",
                        "target": "KRAS G12D",
                        "tool": "refua_admet_profile",
                        "score": 83.9,
                        "promising": True,
                        "assessment": "ADMET profile remains favorable after cross-check.",
                        "metrics": {"binding_probability": 0.84, "admet_score": 0.78},
                        "admet": {
                            "status": "favorable",
                            "key_metrics": {"admet_score": 0.78, "safety_score": 0.82},
                        },
                    }
                ],
            },
        )

        payload = self._request("GET", "/api/promising-drugs?limit=20")
        self.assertIn("drugs", payload)
        self.assertIn("summary", payload)
        self.assertIn("facets", payload)
        self.assertEqual(payload["summary"]["total_drugs"], 1)
        self.assertEqual(payload["summary"]["source_jobs_count"], 2)
        self.assertEqual(payload["facets"]["targets"], ["KRAS G12D"])
        self.assertEqual(
            payload["facets"]["tools"],
            ["refua_admet_profile", "refua_affinity"],
        )
        self.assertEqual(payload["drugs"][0]["name"], "Lumotril")
        self.assertEqual(payload["drugs"][0]["seen_count"], 2)
        self.assertEqual(payload["drugs"][0]["source_jobs_count"], 2)
        self.assertEqual(
            payload["drugs"][0]["sources"][0]["objective"],
            "Cross-check Lumotril ADMET",
        )

    def test_structure_file_endpoint(self) -> None:
        structure_path = self.app.config.data_dir / "mock_complex.cif"
        structure_path.write_text(
            "data_mock\n#\nloop_\n_atom_site.group_PDB\nATOM\n",
            encoding="utf-8",
        )

        url_path = quote(str(structure_path), safe="")
        url = f"http://{self.host}:{self.port}/structures/file?path={url_path}"
        request = Request(url, method="GET")
        with urlopen(request, timeout=5) as response:
            body = response.read().decode("utf-8")
            self.assertEqual(response.status, 200)
            self.assertEqual(response.headers.get_content_type(), "chemical/x-cif")
            self.assertIn("data_mock", body)

    def test_validate_plan_endpoint(self) -> None:
        payload = self._request(
            "POST",
            "/api/plan/validate",
            {
                "plan": {"calls": [{"tool": "refua_validate_spec", "args": {}}]},
                "max_calls": 5,
            },
        )
        self.assertTrue(payload["approved"])

    def test_async_run_job(self) -> None:
        run_payload = self._request(
            "POST",
            "/api/run",
            {
                "objective": "Offline dry-run validation",
                "dry_run": True,
                "async_mode": True,
                "plan": {"calls": [{"tool": "refua_validate_spec", "args": {}}]},
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

    def test_execute_plan_job(self) -> None:
        run_payload = self._request(
            "POST",
            "/api/plan/execute",
            {
                "async_mode": True,
                "plan": {"calls": [{"tool": "refua_validate_spec", "args": {}}]},
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

    def test_jobs_endpoint_includes_live_progress_payload(self) -> None:
        job = self.app.store.create_job(kind="continuous_discovery_cycle", request={"id": 7})
        self.app.store.set_running(job["job_id"])
        self.app.store.update_progress(
            job["job_id"],
            {
                "phase": "planning",
                "summary": "Cycle 7: planning the next discovery run.",
                "cycle_index": 7,
                "phase_elapsed_seconds": 4.2,
                "heartbeat_count": 3,
                "last_heartbeat_at": "2026-03-17T18:00:00+00:00",
            },
        )

        payload = self._request("GET", "/api/jobs?status=running")
        matching = next(
            item for item in payload["jobs"] if item["job_id"] == job["job_id"]
        )
        self.assertEqual(matching["progress"]["phase"], "planning")
        self.assertEqual(matching["progress"]["cycle_index"], 7)
        self.assertEqual(matching["progress"]["heartbeat_count"], 3)

        detail = self._request("GET", f"/api/jobs/{job['job_id']}")
        self.assertEqual(
            detail["progress"]["summary"],
            "Cycle 7: planning the next discovery run.",
        )

    def test_unknown_job_returns_404(self) -> None:
        url = f"http://{self.host}:{self.port}/api/jobs/not-a-real-job"
        request = Request(url, method="GET")
        with self.assertRaises(HTTPError) as ctx:
            urlopen(request, timeout=5)
        error = ctx.exception
        self.assertEqual(error.code, 404)
        _ = error.read()
        error.close()


class StudioAutostartAgentTest(unittest.TestCase):
    @mock.patch("clawcures_ui.app.ContinuousDiscoveryService")
    def test_create_server_starts_continuous_agent_by_default(
        self,
        service_cls: mock.Mock,
    ) -> None:
        tmp = tempfile.TemporaryDirectory()
        config = StudioConfig(
            host="127.0.0.1",
            port=0,
            data_dir=Path(tmp.name) / "data",
            workspace_root=Path(__file__).resolve().parents[2],
            max_workers=1,
            autostart_agent=True,
        )
        server, app = create_server(config)
        try:
            service_cls.assert_called_once()
            service_cls.return_value.start.assert_called_once_with()
        finally:
            server.server_close()
            app.shutdown()
            tmp.cleanup()

    @mock.patch("clawcures_ui.app.ContinuousDiscoveryService")
    def test_create_server_skips_continuous_agent_when_disabled(
        self,
        service_cls: mock.Mock,
    ) -> None:
        tmp = tempfile.TemporaryDirectory()
        config = StudioConfig(
            host="127.0.0.1",
            port=0,
            data_dir=Path(tmp.name) / "data",
            workspace_root=Path(__file__).resolve().parents[2],
            max_workers=1,
            autostart_agent=False,
        )
        server, app = create_server(config)
        try:
            service_cls.assert_not_called()
        finally:
            server.server_close()
            app.shutdown()
            tmp.cleanup()


class StudioApiAuthTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        config = StudioConfig(
            host="127.0.0.1",
            port=0,
            data_dir=Path(self._tmp.name) / "data",
            workspace_root=Path(__file__).resolve().parents[2],
            max_workers=1,
            autostart_agent=False,
            auth_tokens=("viewer-token",),
            operator_tokens=("operator-token",),
            admin_tokens=("admin-token",),
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

    def _request(
        self,
        method: str,
        path: str,
        payload: dict | None = None,
        *,
        token: str | None = None,
        allow_error: bool = False,
    ) -> dict:
        url = f"http://{self.host}:{self.port}{path}"
        data = None
        headers = {}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if token:
            headers["Authorization"] = f"Bearer {token}"

        request = Request(url, method=method, data=data, headers=headers)
        try:
            with urlopen(request, timeout=5) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            body = exc.read().decode("utf-8")
            parsed = json.loads(body) if body else {}
            exc.close()
            if allow_error:
                return {"status_code": exc.code, "body": parsed}
            raise AssertionError(f"HTTP {exc.code} for {path}: {body}") from exc

    def test_auth_required_for_api_get(self) -> None:
        missing = self._request("GET", "/api/health", allow_error=True)
        self.assertEqual(missing["status_code"], 401)

        ok = self._request("GET", "/api/health", token="viewer-token")
        self.assertTrue(ok["ok"])

    def test_post_requires_operator_role(self) -> None:
        payload = {
            "plan": {"calls": [{"tool": "refua_validate_spec", "args": {}}]},
            "max_calls": 10,
            "allow_skip_validate_first": False,
        }
        forbidden = self._request(
            "POST",
            "/api/plan/validate",
            payload,
            token="viewer-token",
            allow_error=True,
        )
        self.assertEqual(forbidden["status_code"], 403)

        allowed = self._request(
            "POST",
            "/api/plan/validate",
            payload,
            token="operator-token",
        )
        self.assertIn("approved", allowed)

    def test_admin_required_for_clear_jobs(self) -> None:
        forbidden = self._request(
            "POST",
            "/api/jobs/clear",
            {"statuses": ["completed"]},
            token="operator-token",
            allow_error=True,
        )
        self.assertEqual(forbidden["status_code"], 403)

        allowed = self._request(
            "POST",
            "/api/jobs/clear",
            {"statuses": ["completed"]},
            token="admin-token",
        )
        self.assertIn("deleted", allowed)


if __name__ == "__main__":
    unittest.main()
