from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


DEFAULT_DATA_DIR_NAME = ".clawcures-ui"
LEGACY_DATA_DIR_NAME = ".refua-studio"


def default_data_dir() -> Path:
    default_path = Path(DEFAULT_DATA_DIR_NAME)
    legacy_path = Path(LEGACY_DATA_DIR_NAME)
    if default_path.exists():
        return default_path
    if legacy_path.exists():
        return legacy_path
    return default_path


@dataclass(frozen=True, slots=True)
class StudioConfig:
    """Runtime configuration for ClawCures UI."""

    host: str = "127.0.0.1"
    port: int = 8787
    data_dir: Path = field(default_factory=default_data_dir)
    max_workers: int = 2
    workspace_root: Path | None = None
    auth_tokens: tuple[str, ...] = ()
    operator_tokens: tuple[str, ...] = ()
    admin_tokens: tuple[str, ...] = ()

    @property
    def static_dir(self) -> Path:
        return Path(__file__).resolve().parent / "static"

    @property
    def database_path(self) -> Path:
        return self.data_dir / "studio.db"

    @property
    def wetlab_database_path(self) -> Path:
        return self.data_dir / "wetlab.sqlite3"

    @property
    def resolved_workspace_root(self) -> Path:
        if self.workspace_root is not None:
            return self.workspace_root.resolve()
        # src/clawcures_ui/config.py -> src -> clawcures-ui -> refua-project
        return Path(__file__).resolve().parents[3]

    @property
    def auth_enabled(self) -> bool:
        return bool(self._all_tokens())

    def roles_for_token(self, token: str) -> frozenset[str]:
        normalized = token.strip()
        if not normalized:
            return frozenset()
        all_tokens = self._all_tokens()
        if normalized not in all_tokens:
            return frozenset()

        roles = {"viewer"}
        if normalized in set(self.operator_tokens):
            roles.add("operator")
        if normalized in set(self.admin_tokens):
            roles.add("admin")
            roles.add("operator")
        return frozenset(roles)

    def _all_tokens(self) -> frozenset[str]:
        tokens: set[str] = set()
        tokens.update(item.strip() for item in self.auth_tokens if item.strip())
        tokens.update(item.strip() for item in self.operator_tokens if item.strip())
        tokens.update(item.strip() for item in self.admin_tokens if item.strip())
        return frozenset(tokens)
