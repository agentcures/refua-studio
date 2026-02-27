from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from refua_studio.program_store import ProgramStore


class ProgramStoreTest(unittest.TestCase):
    def test_program_graph_flow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = ProgramStore(Path(tmp) / "studio.db")

            program = store.upsert_program(
                program_id="prog-1",
                name="Program One",
                indication="Oncology",
                target="KRAS",
                stage="hit_to_lead",
                owner="team-a",
                metadata={"priority": "high"},
            )
            self.assertEqual(program["program_id"], "prog-1")
            self.assertEqual(program["name"], "Program One")

            event = store.add_event(
                program_id="prog-1",
                event_type="campaign_run",
                title="Run submitted",
                status="queued",
                source="test",
                run_id="job-1",
                payload={"objective": "test"},
            )
            self.assertEqual(event["program_id"], "prog-1")
            self.assertEqual(event["event_type"], "campaign_run")
            self.assertTrue(
                store.has_event_for_run(
                    program_id="prog-1",
                    run_id="job-1",
                    status="queued",
                    event_type="campaign_run",
                )
            )

            approval = store.add_approval(
                program_id="prog-1",
                gate="stage_gate",
                decision="approved",
                signer="user-a",
                signature="sig-123",
                rationale="Looks good",
                metadata={"phase": "preclinical"},
            )
            self.assertEqual(approval["decision"], "approved")

            counts = store.counts()
            self.assertEqual(counts["programs"], 1)
            self.assertEqual(counts["events"], 1)
            self.assertEqual(counts["approvals"], 1)


if __name__ == "__main__":
    unittest.main()
