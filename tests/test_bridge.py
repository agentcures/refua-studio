from __future__ import annotations

import sys
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


if __name__ == "__main__":
    unittest.main()
