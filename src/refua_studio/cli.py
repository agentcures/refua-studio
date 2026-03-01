from __future__ import annotations

import argparse
import os
import webbrowser
from pathlib import Path

from refua_studio.app import create_server
from refua_studio.config import StudioConfig


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="refua-studio",
        description="Refua Studio web control plane.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Bind host")
    parser.add_argument("--port", type=int, default=8787, help="Bind port")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(".refua-studio"),
        help="Directory for Studio state and sqlite DB",
    )
    parser.add_argument(
        "--workspace-root",
        type=Path,
        default=None,
        help="Workspace root containing refua-* projects",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=2,
        help="Max background workers for jobs",
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
            "Can also be set via REFUA_STUDIO_AUTH_TOKENS."
        ),
    )
    parser.add_argument(
        "--operator-token",
        action="append",
        default=None,
        help=(
            "Operator bearer token for write endpoints (repeatable). "
            "Can also be set via REFUA_STUDIO_OPERATOR_TOKENS."
        ),
    )
    parser.add_argument(
        "--admin-token",
        action="append",
        default=None,
        help=(
            "Admin bearer token for privileged endpoints (repeatable). "
            "Can also be set via REFUA_STUDIO_ADMIN_TOKENS."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    auth_tokens = _resolve_tokens(args.auth_token, env_name="REFUA_STUDIO_AUTH_TOKENS")
    operator_tokens = _resolve_tokens(
        args.operator_token, env_name="REFUA_STUDIO_OPERATOR_TOKENS"
    )
    admin_tokens = _resolve_tokens(
        args.admin_token, env_name="REFUA_STUDIO_ADMIN_TOKENS"
    )

    config = StudioConfig(
        host=args.host,
        port=args.port,
        data_dir=args.data_dir,
        workspace_root=args.workspace_root,
        max_workers=max(1, int(args.max_workers)),
        auth_tokens=auth_tokens,
        operator_tokens=operator_tokens,
        admin_tokens=admin_tokens,
    )

    server, app = create_server(config)
    host, port = server.server_address
    url = f"http://{host}:{port}"
    print(f"Refua Studio listening on {url}")
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
        print("\nShutting down Refua Studio...")
    finally:
        server.shutdown()
        server.server_close()
        app.shutdown()

    return 0


def _resolve_tokens(values: list[str] | None, *, env_name: str) -> tuple[str, ...]:
    combined: list[str] = []
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


if __name__ == "__main__":
    raise SystemExit(main())
