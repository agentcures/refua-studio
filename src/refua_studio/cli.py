from __future__ import annotations

import argparse
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
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    config = StudioConfig(
        host=args.host,
        port=args.port,
        data_dir=args.data_dir,
        workspace_root=args.workspace_root,
        max_workers=max(1, int(args.max_workers)),
    )

    server, app = create_server(config)
    host, port = server.server_address
    url = f"http://{host}:{port}"
    print(f"Refua Studio listening on {url}")
    print(f"Data directory: {config.data_dir.resolve()}")

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


if __name__ == "__main__":
    raise SystemExit(main())
