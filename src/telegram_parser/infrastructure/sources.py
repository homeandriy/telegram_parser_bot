"""Telegram sources: authenticated MTProto and public web preview."""

from __future__ import annotations

import asyncio
import re
from datetime import datetime

import httpx
from bs4 import BeautifulSoup
from telethon import TelegramClient

from ..core.config import ChannelConfig, Settings
from ..domain.models import TelegramMessage


class TelethonSource:
    def __init__(self, settings: Settings, message_limit: int = 10) -> None:
        if not settings.api_id or not settings.api_hash:
            raise ValueError("telethon.api_id and telethon.api_hash are required for Telethon channels")
        self.settings = settings
        self.message_limit = message_limit

    async def fetch(self, channel: ChannelConfig) -> list[TelegramMessage]:
        messages: list[TelegramMessage] = []
        async with TelegramClient(self.settings.session_path, self.settings.api_id, self.settings.api_hash) as client:
            async for item in client.iter_messages(channel.username, limit=self.message_limit):
                if not item.message:
                    continue
                messages.append(
                    TelegramMessage(
                        source="telethon",
                        channel=channel.username,
                        external_id=str(item.id),
                        text=item.message,
                        published_at=item.date,
                    url=f"https://t.me/{channel.username}/{item.id}",
                    media_urls=(),
                    video_urls=(),
                    )
                )
        return messages


class PublicPreviewSource:
    """Fetch public channel previews, paginating at a conservative request rate."""

    def __init__(self, message_limit: int = 200) -> None:
        self.message_limit = message_limit

    async def fetch(self, channel: ChannelConfig) -> list[TelegramMessage]:
        base_url = f"https://t.me/s/{channel.username}"
        before: int | None = None
        seen: dict[str, TelegramMessage] = {}
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            while len(seen) < self.message_limit:
                url = base_url if before is None else f"{base_url}?before={before}"
                response = await client.get(url, headers={"User-Agent": "TelegramAlertMonitor/0.1"})
                response.raise_for_status()
                page = self._parse_page(channel, response.text)
                new_messages = [message for message in page if message.external_id not in seen]
                if not new_messages:
                    break
                for message in new_messages:
                    seen[message.external_id] = message
                oldest = min(int(message.external_id) for message in new_messages)
                before = oldest
                if len(seen) < self.message_limit:
                    await asyncio.sleep(1.5)
        return sorted(seen.values(), key=lambda message: int(message.external_id), reverse=True)[: self.message_limit]

    @staticmethod
    def _parse_page(channel: ChannelConfig, html: str) -> list[TelegramMessage]:
        soup = BeautifulSoup(html, "html.parser")
        messages: list[TelegramMessage] = []
        for node in soup.select("div.tgme_widget_message_wrap"):
            post = node.select_one("div[data-post]")
            if post is None or not post.get("data-post"):
                continue
            identity = str(post["data-post"])
            _, message_id = identity.rsplit("/", 1)
            text_node = node.select_one("div.tgme_widget_message_text")
            date_node = node.select_one("time")
            media_urls: list[str] = []
            for image in node.select("img[src]"):
                media_urls.append(str(image["src"]))
            for photo in node.select(".tgme_widget_message_photo_wrap[style]"):
                match = re.search(r"url\(['\"]?([^'\")]+)", str(photo["style"]))
                if match:
                    media_urls.append(match.group(1))
            video_urls = [str(video["src"]) for video in node.select("video[src], source[src]")]
            for video in node.select("[data-video]"):
                video_urls.append(str(video["data-video"]))
            date: datetime | None = None
            if date_node is not None and date_node.get("datetime"):
                date = datetime.fromisoformat(str(date_node["datetime"]).replace("Z", "+00:00"))
            messages.append(
                TelegramMessage(
                    source="public",
                    channel=channel.username,
                    external_id=message_id,
                    text=text_node.get_text(" ", strip=True) if text_node else "",
                    published_at=date,
                    url=f"https://t.me/{identity}",
                    media_urls=tuple(dict.fromkeys(media_urls)),
                    video_urls=tuple(dict.fromkeys(video_urls)),
                )
            )
        return messages
