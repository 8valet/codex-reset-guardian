from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from . import __version__
from .appserver import CodexAppServer, read_limits
from .config import default_paths, load_config
from .daemon import GuardianDaemon
from .notifications import build_manager
from .snapshot import available_credits, usage_windows
from .store import Store


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reset-guardian",
        description="Monitor and protect expiring banked Codex resets.",
    )
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--version", action="version", version=__version__)

    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("run", "status", "arm", "disarm", "repin", "notify-test"):
        subparsers.add_parser(command)

    logs = subparsers.add_parser("logs")
    logs.add_argument("-n", "--limit", type=int, default=50)

    for command in ("mute", "unmute"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("credit_id", nargs="?")

    return parser


def _fmt(timestamp: int | None) -> str:
    if not timestamp:
        return "unknown"
    return (
        datetime.fromtimestamp(int(timestamp))
        .astimezone()
        .strftime("%Y-%m-%d %H:%M:%S %Z")
    )


def _runtime(config_path: Path | None) -> tuple[dict, Store]:
    paths = default_paths()
    config = load_config(config_path or paths.config)
    store = Store(paths.state_dir / "guardian.db")
    return config, store


def _live(store: Store):
    snapshot = read_limits()
    account_id = snapshot.get("accountId")
    if not account_id:
        raise RuntimeError("Codex did not return accountId")

    store.pin_account(str(account_id))
    count, credits = available_credits(snapshot)
    store.sync_credits(credits)
    return snapshot, count, credits


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config, store = _runtime(args.config)

    if args.command == "run":
        notifier = build_manager(config)
        GuardianDaemon(
            store,
            config,
            read_limits,
            CodexAppServer,
            notifier,
        ).run_forever()
        return 0

    if args.command == "disarm":
        store.set_armed(False)
        print("Guardian DISARMED")
        return 0

    if args.command == "notify-test":
        notifier = build_manager(config)
        results = notifier.send(
            {
                "severity": "info",
                "title": "Codex Reset Guardian test",
                "message": "Notification delivery is configured.",
                "data": {},
                "dedupe_key": "manual-test",
            }
        )
        if not results:
            print("No notification channels are enabled.")
            return 1
        for name, ok, error in results:
            status = "ok" if ok else f"failed: {error}"
            print(f"{name}: {status}")
        return 0 if any(ok for _, ok, _ in results) else 1

    if args.command == "logs":
        for row in store.recent_events(args.limit):
            details = f" {row.get('details')}" if row.get("details") else ""
            print(
                f"{_fmt(row.get('ts'))} "
                f"{row.get('level', 'INFO')} "
                f"{row.get('event', 'event')}"
                f"{details}"
            )
        return 0

    if args.command == "repin":
        snapshot = read_limits()
        account_id = snapshot.get("accountId")
        if not account_id:
            raise RuntimeError("Codex did not return accountId")
        store.repin(str(account_id))
        print("Account pin updated. Guardian is DISARMED.")
        return 0

    snapshot, count, credits = _live(store)

    if args.command == "status":
        print(f"Codex Reset Guardian v{__version__}")
        print("Guardian:", "ARMED" if store.is_armed() else "DISARMED")
        for window in usage_windows(snapshot):
            print(
                f"{window.name}: {window.remaining_percent:g}% remaining "
                f"(used {window.used_percent:g}%), refresh {_fmt(window.resets_at)}"
            )
        print(f"Banked resets: {count}")
        for credit in credits:
            credit_id = str(credit["id"])
            muted = " (muted)" if store.is_muted(credit_id) else ""
            print(
                f"- {credit.get('title') or 'Reset'} [{credit_id}] "
                f"expires {_fmt(credit['expiresAt'])}{muted}"
            )
        if count > len(credits):
            print(
                "WARNING: reset details available for only "
                f"{len(credits)} of {count}"
            )
        return 0

    if args.command == "arm":
        store.set_armed(True)
        print("Guardian ARMED")
        return 0

    if args.command in {"mute", "unmute"}:
        credit_id = args.credit_id or (
            str(credits[0]["id"]) if credits else None
        )
        if not credit_id or not any(
            str(credit.get("id")) == credit_id for credit in credits
        ):
            raise RuntimeError("banked reset is not currently available")

        muted = args.command == "mute"
        store.set_muted(credit_id, muted)
        action = "Muted" if muted else "Unmuted"
        print(f"{action} reminders for {credit_id}")
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
