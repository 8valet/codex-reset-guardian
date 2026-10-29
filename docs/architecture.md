# Architecture

Codex Reset Guardian is intentionally small and conservative. It is split into a few boundaries so account actions, notification failures, and protocol parsing stay isolated from each other.

## Components

### App Server transport

`src/codex_reset_guardian/appserver.py`

Starts the locally installed `codex app-server --stdio` process and communicates with it through JSON-RPC. Background-service installers pin the resolved Codex executable in `CODEX_RESET_GUARDIAN_CODEX` so the daemon does not depend on an interactive-shell PATH.

### Snapshot parsing

`src/codex_reset_guardian/snapshot.py`

Normalizes usage windows and available banked-reset details. Missing or malformed usage is treated as unknown rather than invented as zero usage.

### Policy

`src/codex_reset_guardian/policy.py`

Decides whether a reminder, eligibility transition, or terminal event should be emitted. Policy code does not perform network or account actions.

### Durable state

`src/codex_reset_guardian/store.py`

Stores account pinning, armed state, reset metadata, idempotency keys, reminder state, sent-event deduplication, logs, and the notification retry outbox in a per-user SQLite database.

### Redemption

`src/codex_reset_guardian/redemption.py`

Performs the safety-critical consume request. Before consuming, the same App Server connection re-checks the pinned account and confirms the exact requested credit is present. Idempotency keys are persisted before the request is sent.

### Daemon

`src/codex_reset_guardian/daemon.py`

Coordinates polling, reminders, outbox delivery, preflight, retry cadence, and optional redemption. Fresh installs are DISARMED.

### Notification adapters

`src/codex_reset_guardian/notifications.py`

Supports desktop, ntfy, Gotify, Telegram, Discord, and generic webhooks. Provider failures are isolated from the monitoring loop and queued for later retry when no configured channel succeeds.

## Safety invariants

1. Automatic redemption is opt-in.
2. Account changes disarm Guardian.
3. Unknown or incomplete target details fail closed.
4. A consume attempt always names a specific credit.
5. The consume connection re-verifies the account and exact target immediately before the account action.
6. A lost response reuses the persisted idempotency key.
7. Reminder mute never disables redemption or terminal-result reporting.
8. Notification failures never authorize or trigger additional account actions.

## Supported platforms

The Python core is platform-neutral. Background helpers provide:

- Linux: systemd user service
- macOS: LaunchAgent
- Windows: per-user Task Scheduler job

All helpers run as the same OS user that owns the Codex login.
