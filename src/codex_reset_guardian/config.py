from __future__ import annotations

import copy
import os
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULTS = {
    "guardian": {
        "redeem_before_seconds": 90,
        "preflight_before_seconds": 300,
        "network_retry_seconds": 10,
        "poll_far_seconds": 1800,
        "poll_day_seconds": 600,
        "poll_hour_seconds": 120,
        "poll_ten_min_seconds": 30,
    },
    "reminders": {
        "enabled": True,
        "checkpoints_seconds": [86400, 21600, 5400, 900],
    },
    "notifications": {},
}


@dataclass(frozen=True)
class Paths:
    config: Path
    state_dir: Path


def default_paths(
    platform_name: str | None = None,
    env: dict[str, str] | None = None,
    home: Path | None = None,
) -> Paths:
    platform_name = (platform_name or sys.platform).lower()
    env = env or os.environ
    home = home or Path.home()

    if platform_name.startswith("win") or platform_name == "windows":
        config_root = Path(env.get("APPDATA", home / "AppData/Roaming"))
        state_root = Path(env.get("LOCALAPPDATA", home / "AppData/Local"))
        return Paths(
            config_root / "codex-reset-guardian" / "config.toml",
            state_root / "codex-reset-guardian",
        )

    if platform_name in {"darwin", "macos"}:
        root = home / "Library" / "Application Support" / "codex-reset-guardian"
        return Paths(root / "config.toml", root)

    config_root = Path(env.get("XDG_CONFIG_HOME", home / ".config"))
    state_root = Path(env.get("XDG_STATE_HOME", home / ".local/state"))
    return Paths(
        config_root / "codex-reset-guardian" / "config.toml",
        state_root / "codex-reset-guardian",
    )


def _merge(destination: dict[str, Any], source: dict[str, Any]) -> None:
    for key, value in source.items():
        if isinstance(value, dict) and isinstance(destination.get(key), dict):
            _merge(destination[key], value)
        else:
            destination[key] = value


def load_config(path: Path | None = None) -> dict[str, Any]:
    config = copy.deepcopy(DEFAULTS)
    target = Path(path) if path is not None else default_paths().config

    if target.exists():
        with target.open("rb") as handle:
            raw = tomllib.load(handle)
        _merge(config, raw)

    guardian = config["guardian"]
    if int(guardian["redeem_before_seconds"]) < 30:
        raise ValueError("redeem_before_seconds must be >= 30")
    if int(guardian["preflight_before_seconds"]) <= int(
        guardian["redeem_before_seconds"]
    ):
        raise ValueError(
            "preflight_before_seconds must be greater than redeem_before_seconds"
        )

    for key in (
        "network_retry_seconds",
        "poll_far_seconds",
        "poll_day_seconds",
        "poll_hour_seconds",
        "poll_ten_min_seconds",
    ):
        if int(guardian[key]) <= 0:
            raise ValueError(f"{key} must be positive")

    raw_checkpoints = config.get("reminders", {}).get(
        "checkpoints_seconds",
        [],
    )
    if not isinstance(raw_checkpoints, list) or not raw_checkpoints:
        raise ValueError(
            "reminders.checkpoints_seconds must be a non-empty list"
        )

    checkpoints = [int(value) for value in raw_checkpoints]
    if any(value <= 0 for value in checkpoints):
        raise ValueError("reminder checkpoints must be positive")
    config["reminders"]["checkpoints_seconds"] = sorted(
        set(checkpoints),
        reverse=True,
    )

    return config
