# Security policy

## Private reporting

Do not publish security vulnerabilities in GitHub Issues, discussions, pull requests, or workflow logs.

Report a suspected vulnerability directly to the repository owner through a private communication channel. Include only the minimum reproduction details needed to verify the issue. Never include production credentials, access tokens, customer documents, database exports, server addresses, or personal data.

## Supported version

Only the current `main` branch and the current production deployment are supported.

## Secret handling

- Production secrets belong only in GitHub Actions secrets or the server's root-owned `.env` file.
- Never commit credentials, tokens, private keys, database dumps, uploaded project documents, or production logs.
- Treat every credential exposed in chat, a screenshot, a workflow log, or Git history as compromised and rotate it.
- Use test-only credentials in local examples and automated tests.

## Response

The repository owner will validate the report, rotate affected credentials immediately, and issue a patched deployment before disclosing technical details.
