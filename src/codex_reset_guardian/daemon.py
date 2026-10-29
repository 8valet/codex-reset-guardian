from __future__ import annotations

import json
import subprocess
import sys
import time
from typing import Any, Callable

from .policy import eligibility, reminder_event, terminal_event
from .redemption import attempt_redeem
from .snapshot import available_credits, usage_windows
from .store import Store


def slots_for(redeem_before: int) -> list[int]:
    """Return consume-attempt slots, never earlier than the configured target."""
    target = int(redeem_before)
    return [
        slot
        for slot in sorted({target, 60, 30}, reverse=True)
        if slot <= target
    ]


def active_slot(remaining: int, redeem_before: int) -> int | None:
    slots = slots_for(redeem_before)
    for index, slot in enumerate(slots):
        lower = slots[index + 1] if index + 1 < len(slots) else 0
        if lower < remaining <= slot:
            return slot
    return None


def clock_synchronized() -> bool | None:
    if not sys.platform.startswith("linux"):
        return None

    try:
        result = subprocess.run(
            ["timedatectl", "show", "-p", "NTPSynchronized", "--value"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except Exception:
        return None

    if result.returncode != 0:
        return None

    value = result.stdout.strip().lower()
    if value == "yes":
        return True
    if value == "no":
        return False
    return None


class GuardianDaemon:
    def __init__(
        self,
        store: Store,
        config: dict[str, Any],
        read_limits: Callable[[], dict[str, Any]],
        rpc_factory: Callable[[], Any],
        notifier: Any,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.store = store
        self.config = config
        self.read_limits = read_limits
        self.rpc_factory = rpc_factory
        self.notifier = notifier
        self.clock = clock

    def _deliver(self, event: dict[str, Any]) -> bool:
        key = str(event["dedupe_key"])
        if self.store.event_was_sent(key):
            self.store.remove_pending_notification(key)
            return True

        results = self.notifier.send(event)
        failures: list[str] = []
        for name, ok, error in results:
            if ok:
                continue
            failures.append(f"{name}: {error}")
            self.store.log("WARN", "notification-failed", f"{name}: {error}")

        delivered = not results or any(ok for _, ok, _ in results)
        if delivered:
            self.store.mark_event_sent(key)
            self.store.remove_pending_notification(key)
        else:
            self.store.mark_notification_failed(
                key,
                "; ".join(failures) or "all notification channels failed",
            )
        return delivered

    def _emit(self, event: dict[str, Any]) -> bool:
        key = str(event["dedupe_key"])
        if self.store.event_was_sent(key):
            return True
        self.store.queue_notification(event)
        return self._deliver(event)

    def _flush_outbox(self) -> None:
        for event in self.store.pending_notifications():
            self._deliver(event)

    def _finish_previous(
        self,
        previous: dict[str, Any],
        current: dict[str, Any] | None,
        now: int,
    ) -> None:
        event = terminal_event(
            previous,
            current,
            self.store.attempts_for(str(previous["id"])),
            now,
        )
        if event:
            self._emit(event)

    def _poll_sleep(self, remaining: int) -> int:
        guardian = self.config["guardian"]
        if remaining > 86400:
            base = int(guardian["poll_far_seconds"])
        elif remaining > 3600:
            base = int(guardian["poll_day_seconds"])
        elif remaining > 600:
            base = int(guardian["poll_hour_seconds"])
        else:
            base = int(guardian["poll_ten_min_seconds"])

        preflight = int(guardian["preflight_before_seconds"])
        if remaining > preflight:
            base = min(base, max(1, remaining - preflight))
        return max(1, base)

    def tick(self) -> int:
        self._flush_outbox()

        now = int(self.clock())
        snapshot = self.read_limits()
        account_id = snapshot.get("accountId")
        if not account_id:
            raise RuntimeError(
                "Codex did not return accountId; refusing autonomous redemption"
            )

        self.store.pin_account(str(account_id))
        count, credits = available_credits(snapshot)
        self.store.sync_credits(credits)
        windows = usage_windows(snapshot)

        partial_details = count > len(credits)
        current = credits[0] if credits else None
        previous_raw = self.store.get_meta("last_credit_json")
        previous = json.loads(previous_raw) if previous_raw else None

        if (
            previous
            and (
                not current
                or str(current.get("id")) != str(previous.get("id"))
            )
            and not partial_details
        ):
            self._finish_previous(previous, current, now)

        if not current:
            if partial_details:
                return int(self.config["guardian"]["poll_day_seconds"])
            if previous and int(previous.get("expiresAt") or 0) <= now:
                self.store.set_meta("last_credit_json", "null")
            return int(self.config["guardian"]["poll_far_seconds"])

        credit_id = str(current["id"])
        remaining = max(0, int(current["expiresAt"]) - now)
        prior = self.store.reminder_state(credit_id)
        if prior and prior.get("eligibility") is not None:
            prior["eligibility"] = bool(prior["eligibility"])

        reminders = self.config.get("reminders", {})
        if reminders.get("enabled", True):
            event = reminder_event(
                current,
                windows,
                now,
                prior,
                self.store.is_muted(credit_id),
                tuple(
                    int(value)
                    for value in reminders.get(
                        "checkpoints_seconds",
                        [86400, 21600, 5400, 900],
                    )
                ),
            )
            if event:
                self._emit(event)

        self.store.set_reminder_state(
            credit_id,
            remaining,
            eligibility(windows),
        )
        self.store.set_meta(
            "last_credit_json",
            json.dumps(current, separators=(",", ":")),
        )

        if not self.store.is_armed() or self.store.has_terminal_attempt(credit_id):
            return self._poll_sleep(remaining)

        guardian = self.config["guardian"]
        preflight = int(guardian["preflight_before_seconds"])
        redeem_before = int(guardian["redeem_before_seconds"])

        if remaining <= preflight and not self.store.preflight_done(credit_id):
            self.store.mark_preflight(credit_id)
            self.store.log("INFO", "preflight", f"{remaining}s remaining")
            if clock_synchronized() is False:
                outcome = attempt_redeem(
                    self.store,
                    self.rpc_factory,
                    credit_id,
                    preflight,
                    expected_account_id=str(account_id),
                )
                if outcome in {"reset", "alreadyRedeemed", "noCredit"}:
                    return max(1, remaining)
                if outcome == "uncertain":
                    return int(guardian["network_retry_seconds"])

        if remaining <= redeem_before:
            slot = active_slot(remaining, redeem_before)
            if slot is not None:
                outcome = attempt_redeem(
                    self.store,
                    self.rpc_factory,
                    credit_id,
                    slot,
                    expected_account_id=str(account_id),
                )
                self.store.log("INFO", "redemption-result", outcome)
                if outcome == "uncertain":
                    return int(guardian["network_retry_seconds"])

        return self._poll_sleep(remaining)

    def run_forever(self) -> None:
        while True:
            try:
                delay = self.tick()
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                self.store.log("ERROR", "guardian-loop-error", repr(exc))
                delay = 30
            time.sleep(delay)
