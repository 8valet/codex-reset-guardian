from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class UsageWindow:
    name: str
    used_percent: float
    remaining_percent: float
    resets_at: int | None = None


def available_credits(
    snapshot: dict[str, Any],
) -> tuple[int, list[dict[str, Any]]]:
    summary = snapshot.get("rateLimitResetCredits") or {}
    count = int(summary.get("availableCount") or 0)
    credits = [
        credit
        for credit in (summary.get("credits") or [])
        if credit.get("id")
        and credit.get("status") == "available"
        and credit.get("expiresAt") is not None
    ]
    credits.sort(key=lambda credit: int(credit["expiresAt"]))
    return count, credits


def usage_windows(snapshot: dict[str, Any]) -> list[UsageWindow]:
    buckets = snapshot.get("rateLimitsByLimitId") or {}
    rate_limits = buckets.get("codex") or snapshot.get("rateLimits") or {}
    windows: list[UsageWindow] = []

    for key in ("primary", "secondary"):
        window = rate_limits.get(key)
        if not isinstance(window, dict):
            continue

        raw_used = window.get("usedPercent")
        if raw_used is None:
            continue

        try:
            used = float(raw_used)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(used):
            continue

        used = max(0.0, min(100.0, used))
        minutes = window.get("windowDurationMins")
        if minutes == 300:
            name = "5-hour"
        elif minutes == 10080:
            name = "weekly"
        elif minutes:
            name = f"{minutes}-minute"
        else:
            name = key

        windows.append(
            UsageWindow(
                name=name,
                used_percent=used,
                remaining_percent=max(0.0, 100.0 - used),
                resets_at=window.get("resetsAt"),
            )
        )

    return windows
