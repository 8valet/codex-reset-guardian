from __future__ import annotations

from typing import Any

from .snapshot import UsageWindow

CHECKPOINTS = (86400, 21600, 5400, 900)


def eligibility(windows: list[UsageWindow]) -> bool | None:
    if not windows:
        return None
    return any(window.remaining_percent < 80 for window in windows)


def _usage_text(windows: list[UsageWindow]) -> str:
    return " • ".join(
        f"{window.name} {window.remaining_percent:g}% left"
        for window in windows
    )


def _crossed(
    previous: int | None,
    remaining: int,
    checkpoints: tuple[int, ...] = CHECKPOINTS,
) -> int | None:
    if remaining <= 0:
        return None

    candidates = [
        checkpoint
        for checkpoint in checkpoints
        if remaining <= checkpoint
        and (previous is None or previous > checkpoint)
    ]
    return min(candidates) if candidates else None


def _title(checkpoint: int) -> str:
    labels = {
        86400: "24 hours",
        21600: "6 hours",
        5400: "90 minutes",
        900: "15 minutes",
    }
    label = labels.get(checkpoint, f"{checkpoint} seconds")
    return f"Banked reset expires in {label}"


def reminder_event(
    credit: dict[str, Any],
    windows: list[UsageWindow],
    now: int,
    prior: dict[str, Any] | None,
    muted: bool,
    checkpoints: tuple[int, ...] = CHECKPOINTS,
) -> dict[str, Any] | None:
    if muted or not credit.get("id") or credit.get("expiresAt") is None:
        return None

    remaining = max(0, int(credit["expiresAt"]) - int(now))
    prior = prior or {}
    current = eligibility(windows)
    previous = prior.get("eligibility")
    usage = _usage_text(windows)

    if current is True and previous is False:
        return {
            "kind": "ready",
            "severity": "success",
            "title": "Banked reset is ready",
            "message": (
                f"{usage}. Your current Codex usage is eligible for the banked "
                "reset. A natural allowance reset can change this before expiry."
            ),
            "dedupe_key": f"codex.banked-ready:{credit['id']}",
            "data": {
                "credit_id": str(credit["id"]),
                "expires_at": int(credit["expiresAt"]),
            },
        }

    checkpoint = _crossed(
        prior.get("remaining_seconds"),
        remaining,
        checkpoints,
    )
    if checkpoint is None:
        return None
    if checkpoint != 86400 and current is True:
        return None

    if current is None:
        status = (
            "Current eligibility cannot be confirmed from the available Codex "
            "usage snapshot."
        )
    elif current:
        status = (
            "It is currently redeemable. A natural allowance reset can change "
            "this before expiry."
        )
    else:
        status = (
            "More Codex usage may be needed before this banked reset can be "
            "redeemed."
        )

    prefix = f"{usage}. " if usage else ""
    return {
        "kind": "checkpoint",
        "severity": "info" if checkpoint == 86400 else "warning",
        "title": _title(checkpoint),
        "message": prefix + status,
        "checkpoint_seconds": checkpoint,
        "dedupe_key": f"codex.banked-reminder:{credit['id']}:{checkpoint}",
        "data": {
            "credit_id": str(credit["id"]),
            "expires_at": int(credit["expiresAt"]),
            "checkpoint_seconds": checkpoint,
        },
    }


def terminal_event(
    previous_credit: dict[str, Any],
    current_credit: dict[str, Any] | None,
    attempts: list[dict[str, Any]],
    now: int,
) -> dict[str, Any] | None:
    credit_id = str(previous_credit.get("id") or "")
    if not credit_id:
        return None
    if current_credit and str(current_credit.get("id")) == credit_id:
        return None

    relevant = [
        attempt
        for attempt in attempts
        if str(attempt.get("credit_id")) == credit_id
    ]
    outcomes = [str(attempt.get("outcome") or "") for attempt in relevant]
    expired = int(previous_credit.get("expiresAt") or 0) <= now

    if "reset" in outcomes:
        state = "redeemed"
    elif "alreadyRedeemed" in outcomes or "noCredit" in outcomes:
        state = "already_used"
    elif expired and "nothingToReset" in outcomes:
        state = "failed"
    elif expired:
        state = "expired"
    elif relevant and any(not outcome for outcome in outcomes):
        state = "uncertain"
    elif not relevant:
        state = "gone"
    else:
        return None

    titles = {
        "redeemed": "Banked reset redeemed",
        "already_used": "Banked reset already used",
        "failed": "Banked reset could not be redeemed",
        "expired": "Banked reset expired",
        "gone": "Banked reset no longer available",
        "uncertain": "Banked reset outcome uncertain",
    }
    messages = {
        "uncertain": (
            "The banked reset is no longer available after an uncertain "
            "redemption attempt. Check your Codex allowance state before "
            "assuming it was redeemed."
        )
    }

    return {
        "state": state,
        "severity": (
            "success"
            if state in {"redeemed", "already_used"}
            else "info"
            if state == "gone"
            else "warning"
        ),
        "title": titles[state],
        "message": messages.get(state, titles[state] + "."),
        "dedupe_key": f"codex.banked-terminal:{credit_id}:{state}",
        "data": {"credit_id": credit_id},
    }
