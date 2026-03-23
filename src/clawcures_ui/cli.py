from __future__ import annotations

import argparse
import os
import webbrowser
from pathlib import Path

from clawcures_ui.app import create_server
from clawcures_ui.config import LEGACY_DATA_DIR_NAME, StudioConfig, default_data_dir


def build_parser() -> argparse.ArgumentParser:
    default_dir = default_data_dir()
    parser = argparse.ArgumentParser(
        prog="clawcures-ui",
        description="ClawCures UI web control plane.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Bind host")
    parser.add_argument("--port", type=int, default=8787, help="Bind port")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=default_dir,
        help=(
            "Directory for UI state and sqlite DB "
            f"(defaults to .clawcures-ui, or {LEGACY_DATA_DIR_NAME} if it already exists)"
        ),
    )
    parser.add_argument(
        "--workspace-root",
        type=Path,
        default=None,
        help="Workspace root containing sibling ClawCures and refua-* projects",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=2,
        help="Max background workers for jobs",
    )
    parser.add_argument(
        "--no-autostart-agent",
        action="store_true",
        help=(
            "Disable the default continuous discovery agent that starts with the UI. "
            "Can also be controlled with CLAWCURES_UI_AUTOSTART_AGENT "
            "or REFUA_STUDIO_AUTOSTART_AGENT."
        ),
    )
    parser.add_argument(
        "--open-browser",
        action="store_true",
        help="Open browser automatically after startup",
    )
    parser.add_argument(
        "--auth-token",
        action="append",
        default=None,
        help=(
            "Viewer bearer token (repeatable). "
            "Can also be set via CLAWCURES_UI_AUTH_TOKENS "
            "or legacy REFUA_STUDIO_AUTH_TOKENS."
        ),
    )
    parser.add_argument(
        "--operator-token",
        action="append",
        default=None,
        help=(
            "Operator bearer token for write endpoints (repeatable). "
            "Can also be set via CLAWCURES_UI_OPERATOR_TOKENS "
            "or legacy REFUA_STUDIO_OPERATOR_TOKENS."
        ),
    )
    parser.add_argument(
        "--admin-token",
        action="append",
        default=None,
        help=(
            "Admin bearer token for privileged endpoints (repeatable). "
            "Can also be set via CLAWCURES_UI_ADMIN_TOKENS "
            "or legacy REFUA_STUDIO_ADMIN_TOKENS."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    auth_tokens = _resolve_tokens(
        args.auth_token,
        env_names=("CLAWCURES_UI_AUTH_TOKENS", "REFUA_STUDIO_AUTH_TOKENS"),
    )
    operator_tokens = _resolve_tokens(
        args.operator_token,
        env_names=("CLAWCURES_UI_OPERATOR_TOKENS", "REFUA_STUDIO_OPERATOR_TOKENS"),
    )
    admin_tokens = _resolve_tokens(
        args.admin_token,
        env_names=("CLAWCURES_UI_ADMIN_TOKENS", "REFUA_STUDIO_ADMIN_TOKENS"),
    )

    config = StudioConfig(
        host=args.host,
        port=args.port,
        data_dir=args.data_dir,
        workspace_root=args.workspace_root,
        max_workers=max(1, int(args.max_workers)),
        autostart_agent=(
            False
            if bool(args.no_autostart_agent)
            else _resolve_bool_setting(
                env_names=(
                    "CLAWCURES_UI_AUTOSTART_AGENT",
                    "REFUA_STUDIO_AUTOSTART_AGENT",
                ),
                default=True,
            )
        ),
        auth_tokens=auth_tokens,
        operator_tokens=operator_tokens,
        admin_tokens=admin_tokens,
    )

    server, app = create_server(config)
    host, port = server.server_address
    url = f"http://{host}:{port}"
    print(f"ClawCures UI listening on {url}")
    print(f"Data directory: {config.data_dir.resolve()}")
    if config.auth_enabled:
        print("Auth: enabled (bearer tokens required for /api routes)")
    else:
        print("Auth: disabled")

    if args.open_browser:
        webbrowser.open(url)

    try:
        server.serve_forever(poll_interval=0.3)
    except KeyboardInterrupt:
        print("\nShutting down ClawCures UI...")
    finally:
        server.shutdown()
        server.server_close()
        app.shutdown()

    return 0


def _resolve_tokens(
    values: list[str] | None,
    *,
    env_names: tuple[str, ...],
) -> tuple[str, ...]:
    combined: list[str] = []
    for env_name in env_names:
        env_raw = os.environ.get(env_name, "")
        if env_raw.strip():
            combined.extend(_parse_csv_tokens(env_raw))
    if values:
        for item in values:
            combined.extend(_parse_csv_tokens(item))
    deduped: list[str] = []
    seen: set[str] = set()
    for token in combined:
        if token in seen:
            continue
        deduped.append(token)
        seen.add(token)
    return tuple(deduped)


def _parse_csv_tokens(raw: str) -> list[str]:
    tokens: list[str] = []
    for piece in raw.split(","):
        normalized = piece.strip()
        if normalized:
            tokens.append(normalized)
    return tokens


def _resolve_bool_setting(
    *,
    env_names: tuple[str, ...],
    default: bool,
) -> bool:
    for env_name in env_names:
        raw = os.environ.get(env_name, "").strip().lower()
        if not raw:
            continue
        if raw in {"1", "true", "yes", "on"}:
            return True
        if raw in {"0", "false", "no", "off"}:
            return False
        raise ValueError(
            f"{env_name} must be one of: 1, 0, true, false, yes, no, on, off."
        )
    return bool(default)


if __name__ == "__main__":
    raise SystemExit(main())
