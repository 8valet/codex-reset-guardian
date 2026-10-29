from __future__ import annotations

from typing import Any, Callable

from .appserver import RPCError
from .snapshot import available_credits
from .store import AccountChanged, Store

VALID_OUTCOMES = {
    "reset",
    "alreadyRedeemed",
    "nothingToReset",
    "noCredit",
}


def _classify_rpc_error(exc: RPCError) -> str | None:
    text = str(exc).lower()
    if (
        "rate_limit_reset_ineligible" in text
        or "nothingtoreset" in text
        or "nothing_to_reset" in text
    ):
        return "nothingToReset"
    if "no_credit" in text or "nocredit" in text:
        return "noCredit"
    return None


def _verify_target(
    store: Store,
    rpc: Any,
    credit_id: str,
    expected_account_id: str,
) -> str | None:
    snapshot = rpc.request(
        "account/rateLimits/read",
        {"excludeResetCreditDetails": False},
        timeout=25,
    )
    if not isinstance(snapshot, dict):
        return "detailsUnavailable"

    account_id = snapshot.get("accountId")
    if not account_id or str(account_id) != str(expected_account_id):
        store.set_armed(False)
        raise AccountChanged(
            "Codex account changed before redemption; Guardian automatically disarmed"
        )

    count, credits = available_credits(snapshot)
    if any(str(credit.get("id")) == credit_id for credit in credits):
        return None
    if count > len(credits):
        return "detailsUnavailable"
    return "targetMissing"


def attempt_redeem(
    store: Store,
    rpc_factory: Callable[[], Any],
    credit_id: str,
    slot: int,
    *,
    expected_account_id: str | None = None,
) -> str:
    row = None

    try:
        with rpc_factory() as rpc:
            if expected_account_id is not None:
                verification = _verify_target(
                    store,
                    rpc,
                    credit_id,
                    expected_account_id,
                )
                if verification is not None:
                    store.log(
                        "WARN",
                        "redemption-precheck",
                        f"{credit_id}: {verification}",
                    )
                    return verification

            row = store.pending_attempt(credit_id)
            if row is None:
                row = store.attempt(credit_id, slot)
                if row is not None and row["outcome"]:
                    return str(row["outcome"])
                if row is None:
                    row = store.create_attempt(credit_id, slot)

            actual_slot = int(row["slot_seconds"])
            idempotency_key = str(row["idempotency_key"])
            result = rpc.request(
                "account/rateLimitResetCredit/consume",
                {
                    "idempotencyKey": idempotency_key,
                    "creditId": credit_id,
                },
                timeout=30,
            )

        outcome = str((result or {}).get("outcome") or "unknown")
        if outcome not in VALID_OUTCOMES:
            store.update_attempt(
                credit_id,
                actual_slot,
                error=f"unknown consume outcome: {outcome}",
                retry=True,
            )
            return "uncertain"

        store.update_attempt(
            credit_id,
            actual_slot,
            outcome=outcome,
            error=None,
        )
        return outcome

    except AccountChanged:
        raise
    except RPCError as exc:
        if row is None:
            store.log(
                "WARN",
                "redemption-precheck-error",
                str(exc)[:1000],
            )
            return "detailsUnavailable"

        classified = _classify_rpc_error(exc)
        if classified:
            store.update_attempt(
                credit_id,
                int(row["slot_seconds"]),
                outcome=classified,
                error=str(exc)[:1000],
            )
            return classified

        store.update_attempt(
            credit_id,
            int(row["slot_seconds"]),
            error=str(exc)[:1000],
            retry=True,
        )
        return "uncertain"
    except Exception as exc:
        if row is None:
            store.log(
                "WARN",
                "redemption-precheck-error",
                repr(exc)[:1000],
            )
            return "detailsUnavailable"

        store.update_attempt(
            credit_id,
            int(row["slot_seconds"]),
            error=repr(exc)[:1000],
            retry=True,
        )
        return "uncertain"
