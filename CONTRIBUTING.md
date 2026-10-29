# Contributing

Thanks for helping improve Codex Reset Guardian.

## Before you open a pull request

1. Keep changes focused. Avoid browser/token scraping or new credential boundaries unless there is a strong reason.
2. Add or update tests for every behavior change.
3. Run:

   ```bash
   python -m unittest discover -s tests -t . -v
   python -m compileall -q src tests
   ```

4. Never commit real account IDs, banked-reset IDs, notification tokens, cookies, webhook URLs, private IP addresses, or state databases.
5. Protocol changes should link to the corresponding OpenAI Codex source or public documentation.

## Design preferences

- Prefer fail-closed behavior for account actions.
- Keep automatic redemption opt-in.
- Keep notification failures isolated from monitoring/redemption logic.
- Prefer simple HTTP integrations and environment-variable secret indirection over large provider SDKs.
- Keep the core dependency-light. Desktop notification support should remain optional.

## Pull requests

Describe the user-facing behavior, safety implications, and tests you ran. If a change affects redemption timing, account verification, idempotency, or protocol parsing, include a regression test for the exact edge case.

## Security issues

Do not disclose vulnerabilities or sensitive account data in public issues. Follow [SECURITY.md](SECURITY.md) instead.
