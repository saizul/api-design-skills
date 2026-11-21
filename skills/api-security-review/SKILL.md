---
name: api-security-review
description: Security review of an HTTP API against the OWASP API Security Top 10 (2023) - broken object/function level authorization (BOLA/IDOR, BFLA), authentication, mass assignment and excessive data exposure, resource limits and rate limiting, SSRF, misconfiguration and inventory. Scans an OpenAPI spec and maps each risk to concrete code checks and grep patterns. Use when the user asks for an API security review or audit, pentest prep, "is this endpoint secure?", or before exposing an API publicly.
license: MIT
compatibility: Python 3.9+ for the scanner. YAML specs need PyYAML. ripgrep (rg) recommended for code checks.
metadata:
  author: Saizul Amin
  version: "0.1.0"
---

# API security review

A spec scan finds contract-level problems in seconds; most serious API bugs (BOLA,
BFLA, business-flow abuse) live in code. Do both.

Paths such as `scripts/...` and `references/...` are relative to this skill's folder (`${CLAUDE_SKILL_DIR}` in Claude Code). Run scripts from the user's project with that folder's path.

## When to use

- Reviewing an API before launch, a partner integration, or a pentest.
- Reviewing a pull request that adds or changes endpoints.
- The user asks about IDOR/BOLA, mass assignment, rate limiting or SSRF in an API.

## When not to use

- Web front-end issues (XSS, CSRF in server-rendered forms) beyond the API surface.
- Infrastructure hardening (TLS ciphers, WAF rules): mention, do not deep-dive.
- Do not run active attacks against systems the user does not own or has no permission to test.

## Workflow

1. **Scope.** List the API's consumers (public, partner, first-party app), auth method,
   tenancy model (single user, organisations, multi-tenant) and the most sensitive data
   and business flows (payments, account recovery, exports).
2. **Scan the spec** if one exists:

   ```bash
   python scripts/api_security_scan.py openapi.yaml
   python scripts/api_security_scan.py openapi.yaml --format json --min-severity warning
   ```

   Findings are grouped by OWASP category (API1-API10). Exit 1 means findings at or
   above `--fail-on` (default `error`). `info` items such as `object-access-review` are
   a to-do list for step 3, not vulnerabilities.
3. **Review the code** for each category using the checks and `rg` patterns in
   [references/owasp-api-top10.md](references/owasp-api-top10.md). Priority order:
   API1 (object-level authorization on every `{id}` route), API5 (role checks on admin
   and write routes), API3 (field allowlists on input, response serializers on output),
   API2 (token validation, login/reset brute force), API4 (limits), API7 (outbound
   URL fetches), API6 (abuse of sensitive flows), API8, API9, API10.
4. **Verify suspicious findings** with a minimal, safe reproduction against a local or
   staging environment the user controls (for example two test users, request user B's
   object with user A's token). Never use production data or third-party systems.
5. **Report** with severity based on impact and exploitability, not the scanner's label.

## Output

A report with:

1. Scope and assumptions.
2. Findings table: `ID | OWASP | Endpoint/file:line | Severity | Evidence | Fix`.
3. For each High/Critical: reproduction steps (safe), root cause, the code fix, and a
   regression test (for BOLA: "user A gets 404 for user B's object").
4. Categories reviewed with no findings, so coverage is explicit.
5. Scanner summary (counts by category).

## Example prompts

- "Do a security review of our orders API (spec in openapi.yaml, code in src/routes)."
- "Is this endpoint vulnerable to IDOR?"
- "Check our API against the OWASP API Top 10 before launch."
