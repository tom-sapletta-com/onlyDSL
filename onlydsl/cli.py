from __future__ import annotations

import sys


def main() -> None:
    """Dispatch control-plane commands without importing the application runtime."""
    arguments = sys.argv[1:]
    if arguments and arguments[0] == "ssot":
        from onlydsl.ssot.cli import main as ssot_main
        raise SystemExit(ssot_main(arguments[1:]))
    if arguments and arguments[0] == "serve":
        sys.argv = [sys.argv[0], *arguments[1:]]
    from server import main as server_main
    server_main()
