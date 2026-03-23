from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from clawcures_ui.bridge import CampaignBridge


class CampaignBridgeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace_root = Path(__file__).resolve().parents[2]
        self.bridge = CampaignBridge(self.workspace_root)

    def tearDown(self) -> None:
        self.bridge.shutdown()

    def test_default_objective_is_non_empty(self) -> None:
        self.assertTrue(self.bridge.default_objective().strip())

    def test_available_tools_has_known_entries(self) -> None:
        tools, _warnings = self.bridge.available_tools()
        self.assertIn("refua_validate_spec", tools)
        self.assertIn("refua_protein_properties", tools)
        self.assertIn("refua_data_list", tools)

    def test_examples_payload(self) -> None:
        payload = self.bridge.examples()
        self.assertIn("objectives", payload)
        self.assertGreaterEqual(len(payload["objectives"]), 1)
        first = payload["objectives"][0]
        self.assertIn("label", first)
        self.assertIn("objective", first)

    def test_ecosystem_payload(self) -> None:
        payload = self.bridge.ecosystem()
        self.assertIn("products", payload)
        self.assertIn("clawcures", payload)
        self.assertIsInstance(payload["products"], list)
        self.assertGreaterEqual(len(payload["products"]), 1)
        self.assertIn("default_objective", payload["clawcures"])
        self.assertIn("tool_allowlist", payload["clawcures"])

    def test_validate_plan_accepts_simple_valid_plan(self) -> None:
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
        self.assertIn("refua_validate_spec", payload["allowed_tools"])

    def test_validate_plan_rejects_invalid_plan(self) -> None:
        payload = self.bridge.validate_plan(
            plan={
                "calls": [
                    {"tool": "refua_affinity", "args": {}},
                    {"tool": "not_a_real_tool", "args": {}},
                ]
            },
            max_calls=1,
            allow_skip_validate_first=False,
        )
        self.assertFalse(payload["approved"])
        self.assertGreaterEqual(len(payload["errors"]), 1)


if __name__ == "__main__":
    unittest.main()
