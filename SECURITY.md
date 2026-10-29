# Security Policy

## Supported versions

Security fixes are applied to the latest public release line. The first public release is `0.1.x`.

## Reporting a vulnerability

Use GitHub's private **Security advisory / Report a vulnerability** flow for this repository:

https://github.com/8valet/codex-reset-guardian/security/advisories/new

Do **not** open a public issue containing credentials, account identifiers, banked-reset IDs, cookies, tokens, webhook URLs, private IP addresses, or exploit details that could expose another user.

## Trust boundary

Guardian relies on the user's already-authenticated local Codex CLI. It does not need or want ChatGPT passwords, browser cookies, OAuth access tokens, or OpenAI API keys.

Notification-provider credentials should use `env:NAME` indirection where practical. Treat the per-user config and SQLite state database as private user files.

## Consequential action

When armed, Guardian can request redemption of an available banked reset on the pinned Codex account. That is a consequential account action.

Safety controls include:

- fresh installs are DISARMED;
- the first successful live read pins the opaque Codex account ID;
- an account change automatically disarms Guardian;
- consume requests name an exact credit ID;
- the same consume connection re-checks the pinned account and exact credit before redemption;
- idempotency keys are persisted before requests are sent;
- unknown outcomes and incomplete target details fail closed;
- `disarm` does not depend on notification delivery or notification secrets.

## Local-machine assumptions

Reports that require a user to deliberately replace the `codex` executable in their own user environment, modify Guardian's installed source, or provide a malicious local config are generally outside Guardian's security boundary because they already require local-user compromise.

If you are unsure whether something is a vulnerability, report it privately rather than posting potentially sensitive details in a public issue.
