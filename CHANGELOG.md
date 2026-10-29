# Changelog

All notable changes to Codex Reset Guardian are documented here.

## 0.1.0 - 2026-10-30

First public release.

### Added

- Cross-platform Codex App Server transport for Windows, macOS, and Linux.
- Current and legacy Codex usage snapshot parsing.
- Account pinning and DISARMED-by-default automatic redemption.
- Persisted idempotency keys and same-connection account/reset verification before consume.
- Usage-aware 24h / 6h / 90m / 15m reminder policy with per-reset mute.
- Durable notification retry outbox.
- Desktop, ntfy, Gotify, Telegram, Discord, and generic webhook notifications.
- Linux systemd-user, macOS LaunchAgent, and Windows Task Scheduler installers.
- Offline `logs` and `disarm` safety commands.
- User-private Unix state permissions.
- CI across Windows, macOS, and Linux.

### Safety and compatibility

- Unknown consume outcomes fail closed.
- Partial reset-detail responses never invent a target.
- A known exact credit may still be verified safely when the backend caps other detail rows.
- Background installers pin the resolved `codex` executable path so interactive-shell PATH differences do not break the daemon.
