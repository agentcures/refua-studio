from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from refua_studio.storage import JobStore


class JobStoreTest(unittest.TestCase):
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
