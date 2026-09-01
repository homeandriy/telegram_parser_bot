"""One-off collection of configured public Telegram previews."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from ..core.config import load_settings
from ..infrastructure.sources import PublicPreviewSource


async def collect(config_path: Path, limit: int) -> None:
    settings = load_settings(config_path)
    source = PublicPreviewSource(message_limit=limit)
    for channel in settings.channels:
        if channel.source != "public":
            continue
        messages = await source.fetch(channel)
        newest = messages[0].external_id if messages else "—"
        oldest = messages[-1].external_id if messages else "—"
        print(f"{channel.username}: {len(messages)} messages (IDs {oldest}…{newest})")


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect configured public Telegram channels")
    parser.add_argument("--config", type=Path, default=Path("config.example.toml"))
    parser.add_argument("--limit", type=int, default=200)
    args = parser.parse_args()
    asyncio.run(collect(args.config, max(1, args.limit)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
