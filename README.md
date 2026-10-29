<div align="center">

# 🛡️ Codex Reset Guardian

**Protect expiring Codex banked resets with timely reminders and opt-in safe redemption.**

[![CI](https://github.com/8valet/codex-reset-guardian/actions/workflows/ci.yml/badge.svg)](https://github.com/8valet/codex-reset-guardian/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.11%2B-blue)
![Platforms](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Unofficial community utility. Not affiliated with or endorsed by OpenAI.**

</div>

Codex Reset Guardian watches the banked reset attached to your locally authenticated Codex account, warns you before it expires, and can optionally redeem the earliest-expiring reset shortly before the deadline.

It is designed for both:

- **PC users** who want native desktop notifications.
- **Self-hosters** who want ntfy, Gotify, Telegram, Discord, or webhook alerts.

```text
Codex CLI → Reset Guardian → reminders / status / optional redemption
                           ├─ desktop notifications
                           ├─ ntfy / Gotify
                           ├─ Telegram / Discord
                           └─ generic webhook
```

## Quick start

### 1. Requirements

- Python 3.11+
- A current `codex` CLI in `PATH`
- Codex already signed in for the same OS user (`codex login`)

### 2. Install

```bash
git clone https://github.com/8valet/codex-reset-guardian.git
cd codex-reset-guardian
python -m pip install .
```

For native desktop notifications:

```bash
python -m pip install '.[desktop]'
```

`pipx` is also a good fit for an isolated CLI install.

### 3. Check your state

```bash
reset-guardian status
```

Example:

```text
Codex Reset Guardian v0.1.0
Guardian: DISARMED
5-hour: 72% remaining (used 28%)
weekly: 91% remaining (used 9%)
Banked resets: 1
- Full reset [<credit-id>] expires 2026-11-07 01:30:20 +03
```

### 4. Configure notifications

Copy `config.example.toml` to your platform config location, enable the channels you want, then test them:

```bash
reset-guardian notify-test
reset-guardian logs -n 50
```

### 5. Optional: enable automatic redemption

Automatic redemption is **off by default**. Only enable it after you have checked status and notifications:

```bash
reset-guardian arm
```

Disable it at any time—even if notification secrets are broken or unavailable:

```bash
reset-guardian disarm
```

> [!IMPORTANT]
> Arming Guardian allows it to request redemption of a banked reset on your Codex account. Fresh installs are always DISARMED.

## Why this exists

Banked resets expire. The useful moment to redeem one depends on current 5-hour / weekly allowance usage, and a natural allowance refresh can make the reset temporarily ineligible again. Guardian watches that changing state instead of relying on a static calendar reminder.

OpenAI currently documents that a banked reset can be manually used when at least one covered allowance has **less than 80% remaining**. Guardian does not bypass that rule; the Codex backend remains authoritative.

## Safety model

Guardian is deliberately conservative:

- Fresh installs start **DISARMED**.
- The first successful read pins the opaque Codex account ID.
- If the Codex account changes, Guardian automatically disarms.
- Every consume request names a specific credit ID.
- Immediately before redemption, the consume connection re-checks the pinned account and exact target credit.
- Idempotency keys are persisted **before** a request is sent.
- If a response is lost, the same pending key is reused.
- Unknown backend outcomes fail closed.
- Missing/partial reset details do not cause Guardian to guess a target.
- Notification failures do not stop monitoring and are queued for retry.
- No browser cookies, ChatGPT passwords, OpenAI API keys, Selenium, or Playwright are used.

Read [SECURITY.md](SECURITY.md) for the full trust model and [docs/architecture.md](docs/architecture.md) for the component boundaries and safety invariants.

## Reminder behavior

Default checkpoints are approximately:

| Time before expiry | Behavior |
| --- | --- |
| 24 hours | General heads-up |
| 6 hours | Warn if action may be needed |
| 90 minutes | Strong warning if still not eligible |
| 15 minutes | Final action-needed warning |

When usage transitions from ineligible to eligible, Guardian emits one **Banked reset is ready** notification. A later natural allowance refresh can make eligibility change again, so later warnings may reappear when appropriate.

Mute only one reset's reminders:

```bash
reset-guardian mute
```

Or specify its ID:

```bash
reset-guardian mute <credit-id>
reset-guardian unmute <credit-id>
```

Muting reminders does **not** disable automatic redemption and does **not** suppress the final outcome notification.

## Redemption policy

Default policy:

- Read-only preflight at T−5 minutes.
- First consume attempt at T−90 seconds.
- If the backend explicitly reports `nothingToReset`, later fallback slots are T−60 and T−30.
- If the configured initial target is later than T−60, fallback slots are never scheduled earlier than that configured target.
- Uncertain transport/RPC outcomes retry using the persisted idempotency key and `network_retry_seconds` cadence.
- A successful / already-redeemed / no-credit outcome prevents another consume while the backend usage view catches up.

`redeem_before_seconds` is configurable but cannot be below 30 seconds.

## Notification channels

All HTTP channels use simple HTTP requests rather than provider SDKs. Secrets may use `env:VARIABLE_NAME` in TOML so they do not need to live in the config file.

### Desktop

Install `.[desktop]` and enable `[notifications.desktop]`. Desktop notifications depend on OS permission and an active desktop session.

### ntfy

Set a topic URL and optionally `NTFY_TOKEN`.

### Gotify

Set the Gotify base URL and `GOTIFY_TOKEN`.

### Telegram

Set `TELEGRAM_BOT_TOKEN` and your chat ID.

### Discord

Set `DISCORD_WEBHOOK_URL`.

### Generic webhook

Guardian POSTs the normalized event as JSON. Optional headers can also reference environment variables.

> [!NOTE]
> Background services do not always inherit variables exported only in an interactive terminal. Use a persistent user environment for your OS when notification credentials use `env:...` references.

## Run in the background

Install the Python package first, then use the helper for your platform. Installers resolve the current `codex` executable path so the background process does not depend on your interactive shell PATH.

### Linux

```bash
./scripts/install-linux.sh
```

Creates a **systemd user service**. On an always-on server, you may also enable user lingering through your normal system-administration process.

### macOS

```bash
./scripts/install-macos.sh
```

Creates a user LaunchAgent.

### Windows

Run PowerShell as your normal user:

```powershell
.\scripts\install-windows.ps1
```

Creates a per-user Task Scheduler job at logon. Do not install it as SYSTEM; Codex authentication and desktop notifications belong to your user session.

## Config and state locations

| Platform | Config |
| --- | --- |
| Linux | `$XDG_CONFIG_HOME/codex-reset-guardian/config.toml` or `~/.config/codex-reset-guardian/config.toml` |
| macOS | `~/Library/Application Support/codex-reset-guardian/config.toml` |
| Windows | `%APPDATA%\codex-reset-guardian\config.toml` |

State/SQLite is per-user and separate from the repository. On Unix-like systems Guardian creates its state directory as user-only (`0700`) and the database as `0600`.

## CLI

```text
reset-guardian status
reset-guardian run
reset-guardian arm
reset-guardian disarm
reset-guardian repin
reset-guardian mute [credit-id]
reset-guardian unmute [credit-id]
reset-guardian notify-test
reset-guardian logs [-n N]
```

## Self-hosting

Run Guardian directly on the machine where the Codex CLI is already authenticated.

A Docker image is intentionally not provided in v0.1. Mounting Codex authentication into a container creates another credential boundary for little benefit. For headless systems, use ntfy, Gotify, Telegram, Discord, or a generic webhook.

## Protocol compatibility

Guardian uses the local Codex App Server protocol:

- `account/rateLimits/read` with reset-credit details enabled
- `account/rateLimitResetCredit/consume` with `creditId` and `idempotencyKey`

Codex protocol details and promotional reset behavior can change. Guardian fails closed when required target details are unavailable or consume outcomes are unknown.

References:

- [OpenAI — How resets work in Codex](https://help.openai.com/en/articles/20001498-how-resets-work-in-codex)
- [OpenAI Codex source](https://github.com/openai/codex)

## Development

```bash
python -W error::ResourceWarning -m unittest discover -s tests -t . -v
python -m compileall -q src tests
```

CI runs the suite on Windows, macOS, and Linux across supported Python versions.

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md). Please never include account IDs, banked-reset IDs, notification credentials, cookies, or private network details in issues or test fixtures.

## License

MIT — see [LICENSE](LICENSE).
