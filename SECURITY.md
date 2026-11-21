# Security Policy

## Supported versions

| Version | Supported |
| --- | --- |
| 0.1.x | yes |

## What counts as a vulnerability

- A helper script that executes code or follows instructions from the file it analyses
  (for example, from an OpenAPI document or a webhook body).
- A script that prints, logs or writes a secret (webhook secrets are read from an
  environment variable or file and must never be echoed).
- A script that makes network requests. None of the scripts should touch the network.
- Example or reference code in a skill that is insecure as written in a way the text does
  not warn about (for example a signature check that is not constant-time, or an
  idempotency example that lets one tenant replay another tenant's response).
- A skill instruction that would lead an agent to take a destructive or unsafe action
  without asking the user.

Disagreements about API design advice are not vulnerabilities; please open a normal issue.

## Reporting

Please **do not** open a public issue. Use
[GitHub private vulnerability reporting](https://github.com/saizul/api-design-skills/security/advisories/new)
with the affected skill or file, the impact and steps to reproduce. Do not include real
secrets or production data.

You will get an answer within 5 working days. Fixes are released as soon as possible and
credited in the changelog unless you prefer otherwise.

## Using the skills safely

- Read a skill's `SKILL.md` and scripts before installing it, as with any code you run.
- Run the scanners on copies of specs; they only read files and print reports.
- Keep webhook secrets in environment variables or files with tight permissions.
