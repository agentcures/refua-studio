from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class StudioConfig:
    """Runtime configuration for Refua Studio."""

    host: str = "127.0.0.1"
    port: int = 8787
    data_dir: Path = Path(".refua-studio")
    max_workers: int = 2
    workspace_root: Path | None = None

    @property
    def static_dir(self) -> Path:
        return Path(__file__).resolve().parent / "static"

    @property
    def database_path(self) -> Path:
        return self.data_dir / "studio.db"

    @property
    def resolved_workspace_root(self) -> Path:
        if self.workspace_root is not None:
            return self.workspace_root.resolve()
        # src/refua_studio/config.py -> src -> refua-studio -> refua-project
        return Path(__file__).resolve().parents[3]
