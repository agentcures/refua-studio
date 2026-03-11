from __future__ import annotations

import os
import sys
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from clawcures_ui.cli import _resolve_tokens
from refua_studio.app import create_server


class CompatibilityTest(unittest.TestCase):
    def test_pyproject_declares_refua_mcp_dependency(self) -> None:
        pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        dependencies = pyproject["project"]["dependencies"]
        self.assertTrue(
            any(str(dep).startswith("refua-mcp") for dep in dependencies),
            "clawcures-ui must declare refua-mcp so execution environments install MCP runtime deps.",
        )

    def test_pyproject_python_range_matches_refua_mcp_support(self) -> None:
        pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        project = pyproject["project"]
        self.assertIn(
            "<3.14",
            str(project["requires-python"]),
            "clawcures-ui cannot claim Python 3.14 support while live execution depends on refua-mcp.",
        )
        self.assertFalse(
            any(str(item).strip() == "Programming Language :: Python :: 3.14" for item in project["classifiers"]),
            "clawcures-ui classifiers must not advertise Python 3.14 support.",
        )

    def test_legacy_module_alias_still_exports_server_factory(self) -> None:
        self.assertTrue(callable(create_server))

    def test_legacy_auth_env_vars_are_still_accepted(self) -> None:
        previous = os.environ.get("REFUA_STUDIO_AUTH_TOKENS")
        os.environ["REFUA_STUDIO_AUTH_TOKENS"] = " legacy-one , legacy-two "
        try:
            tokens = _resolve_tokens(None, env_names=("CLAWCURES_UI_AUTH_TOKENS", "REFUA_STUDIO_AUTH_TOKENS"))
        finally:
            if previous is None:
                os.environ.pop("REFUA_STUDIO_AUTH_TOKENS", None)
            else:
                os.environ["REFUA_STUDIO_AUTH_TOKENS"] = previous
        self.assertEqual(tokens, ("legacy-one", "legacy-two"))


if __name__ == "__main__":
    unittest.main()
