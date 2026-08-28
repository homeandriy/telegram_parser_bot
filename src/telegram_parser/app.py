"""CLI entry point; UI and daemon share the same source adapters."""

from __future__ import annotations

import argparse
from pathlib import Path

from .config import load_settings
from .monitor import run_daemon
from .state import StateRepository
from .ui import run_ui


def main() -> int:
    parser = argparse.ArgumentParser(description="Telegram Alert Monitor")
    parser.add_argument("--daemon", action="store_true", help="Run the PostgreSQL-backed Ubuntu daemon")
    parser.add_argument("--config", type=Path, default=Path("config.toml"), help="Daemon TOML configuration")
    parser.add_argument("--state-dir", type=Path, help="UI configuration directory")
    args = parser.parse_args()
    if args.daemon:
        state_dir = args.state_dir or args.config.parent / "state"
        run_daemon(load_settings(args.config), StateRepository(state_dir))
        return 0
    return run_ui(StateRepository(args.state_dir))


if __name__ == "__main__":
    raise SystemExit(main())
