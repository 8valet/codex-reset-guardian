from __future__ import annotations

import json
import os
from typing import Any, Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

Opener = Callable[..., Any]


def resolve_value(value: str | None) -> str | None:
    if value is None:
        return None
    if value.startswith("env:"):
        name = value[4:]
        resolved = os.environ.get(name)
        if not resolved:
            raise ValueError(f"environment variable {name} is not set")
        return resolved
    return value


def _json_request(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str] | None = None,
) -> Request:
    base = {
        "Content-Type": "application/json",
        "User-Agent": "codex-reset-guardian/0.1.0",
    }
    base.update(headers or {})
    return Request(
        url,
        data=json.dumps(payload, separators=(",", ":")).encode(),
        headers=base,
        method="POST",
    )


def _send(request: Request, opener: Opener) -> None:
    with opener(request, timeout=10) as response:
        response.read()


class NtfyNotifier:
    name = "ntfy"

    def __init__(
        self,
        url: str,
        token: str | None = None,
        opener: Opener = urlopen,
    ) -> None:
        self.url = url
        self.token = token
        self.opener = opener

    def send(self, event: dict[str, Any]) -> None:
        headers = {
            "Title": event["title"],
            "Tags": (
                "warning"
                if event.get("severity") in {"warning", "error"}
                else "information"
            ),
        }
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        request = Request(
            self.url,
            data=event["message"].encode(),
            headers=headers,
            method="POST",
        )
        _send(request, self.opener)


class GotifyNotifier:
    name = "gotify"

    def __init__(
        self,
        base_url: str,
        token: str,
        opener: Opener = urlopen,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.opener = opener

    def send(self, event: dict[str, Any]) -> None:
        if event.get("severity") == "error":
            priority = 8
        elif event.get("severity") == "warning":
            priority = 5
        else:
            priority = 3
        url = self.base_url + "/message?" + urlencode({"token": self.token})
        _send(
            _json_request(
                url,
                {
                    "title": event["title"],
                    "message": event["message"],
                    "priority": priority,
                },
            ),
            self.opener,
        )


class TelegramNotifier:
    name = "telegram"

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        opener: Opener = urlopen,
        base_url: str = "https://api.telegram.org",
    ) -> None:
        self.bot_token = bot_token
        self.chat_id = str(chat_id)
        self.opener = opener
        self.base_url = base_url.rstrip("/")

    def send(self, event: dict[str, Any]) -> None:
        url = f"{self.base_url}/bot{self.bot_token}/sendMessage"
        _send(
            _json_request(
                url,
                {
                    "chat_id": self.chat_id,
                    "text": f"{event['title']}\n\n{event['message']}",
                },
            ),
            self.opener,
        )


class DiscordNotifier:
    name = "discord"

    def __init__(
        self,
        webhook_url: str,
        opener: Opener = urlopen,
    ) -> None:
        self.webhook_url = webhook_url
        self.opener = opener

    def send(self, event: dict[str, Any]) -> None:
        _send(
            _json_request(
                self.webhook_url,
                {"content": f"**{event['title']}**\n{event['message']}"},
            ),
            self.opener,
        )


class WebhookNotifier:
    name = "webhook"

    def __init__(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        opener: Opener = urlopen,
    ) -> None:
        self.url = url
        self.headers = headers or {}
        self.opener = opener

    def send(self, event: dict[str, Any]) -> None:
        _send(
            _json_request(self.url, event, self.headers),
            self.opener,
        )


class DesktopNotifier:
    name = "desktop"

    def __init__(self, app_name: str = "Codex Reset Guardian") -> None:
        self.app_name = app_name

    def send(self, event: dict[str, Any]) -> None:
        try:
            from desktop_notifier import DesktopNotifierSync as Backend
            from desktop_notifier import Urgency
        except ImportError as exc:
            raise RuntimeError(
                "desktop notifications require: "
                "pip install 'codex-reset-guardian[desktop]'"
            ) from exc

        urgency = (
            Urgency.Critical
            if event.get("severity") == "error"
            else Urgency.Normal
        )
        notifier = Backend(app_name=self.app_name)
        notifier.send(
            title=event["title"],
            message=event["message"],
            urgency=urgency,
        )


class NotificationManager:
    def __init__(self, notifiers: list[Any]) -> None:
        self.notifiers = notifiers

    def send(
        self,
        event: dict[str, Any],
    ) -> list[tuple[str, bool, str | None]]:
        results: list[tuple[str, bool, str | None]] = []
        for notifier in self.notifiers:
            try:
                notifier.send(event)
                results.append((notifier.name, True, None))
            except Exception as exc:
                results.append((notifier.name, False, str(exc)))
        return results


def build_manager(config: dict[str, Any]) -> NotificationManager:
    section = config.get("notifications") or {}
    items: list[Any] = []

    def enabled(name: str) -> bool:
        return bool((section.get(name) or {}).get("enabled", False))

    if enabled("desktop"):
        items.append(DesktopNotifier())

    if enabled("ntfy"):
        item = section["ntfy"]
        items.append(
            NtfyNotifier(
                str(item["url"]),
                resolve_value(item.get("token")),
            )
        )

    if enabled("gotify"):
        item = section["gotify"]
        items.append(
            GotifyNotifier(
                str(item["url"]),
                str(resolve_value(item.get("token")) or ""),
            )
        )

    if enabled("telegram"):
        item = section["telegram"]
        items.append(
            TelegramNotifier(
                str(resolve_value(item.get("bot_token")) or ""),
                str(item["chat_id"]),
            )
        )

    if enabled("discord"):
        item = section["discord"]
        items.append(
            DiscordNotifier(
                str(resolve_value(item.get("webhook_url")) or "")
            )
        )

    if enabled("webhook"):
        item = section["webhook"]
        headers = {
            str(key): str(resolve_value(value) or "")
            for key, value in (item.get("headers") or {}).items()
        }
        items.append(WebhookNotifier(str(item["url"]), headers))

    return NotificationManager(items)
