# api-design-skills

[![CI](https://github.com/saizul/api-design-skills/actions/workflows/ci.yml/badge.svg)](https://github.com/saizul/api-design-skills/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/saizul/api-design-skills?sort=semver)](https://github.com/saizul/api-design-skills/releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/saizul/api-design-skills?style=social)](https://github.com/saizul/api-design-skills/stargazers)

**Agent Skills that help Claude Code and Codex design, review, secure and document HTTP APIs: REST conventions, OpenAPI linting, RFC 9457 errors, pagination, webhooks, idempotency, OWASP API Top 10 and deprecation, with tested helper scripts.**

Each skill is a folder with a `SKILL.md` (the instructions an agent loads when the task
matches), optional `references/` for detail, and deterministic `scripts/` that do the
checking an LLM should not do from memory: linting a spec, verifying an HMAC, building a
`Sunset` header. Scripts use the Python standard library (PyYAML only to read YAML specs),
make no network calls, support `--help` and `--format json`, and exit non-zero on findings
so they also work in CI.

## Skills

| Skill | What it does | Try asking |
| --- | --- | --- |
| [rest-api-design](skills/rest-api-design/SKILL.md) | Resource naming, methods, status codes, payload conventions, versioning; outputs an endpoint table and a must/should review checklist | "Design endpoints for subscriptions, plans and invoices." |
| [openapi-review](skills/openapi-review/SKILL.md) | Lints OpenAPI 3.x (24 rules: operationIds, descriptions, error responses, examples, security, path params, naming) and adds a manual review | "Review our openapi.yaml and fix the gaps." |
| [error-responses](skills/error-responses/SKILL.md) | RFC 9457 problem details: type catalog, validation errors, handlers for Express, FastAPI, Flask, Laravel, PHP; lints error bodies and specs | "Make our API errors consistent and stop leaking stack traces." |
| [pagination-filtering](skills/pagination-filtering/SKILL.md) | Cursor vs offset, keyset SQL, signed cursors, RFC 8288 Link headers, filter/sort conventions; audits list endpoints | "Our offset pagination is slow after page 500. Fix it." |
| [webhook-design](skills/webhook-design/SKILL.md) | Event envelope, Standard Webhooks/GitHub/Stripe signatures, retries, dedup, versioning; sign/verify CLI and Node/PHP snippets tested against published vectors | "Write an endpoint that verifies Stripe webhooks." |
| [idempotency-keys](skills/idempotency-keys/SKILL.md) | `Idempotency-Key` contract, fingerprinting, replay, 409/422 rules, Postgres/MySQL/Redis storage, tested reference implementation | "Customers get charged twice when the app retries." |
| [api-security-review](skills/api-security-review/SKILL.md) | OWASP API Security Top 10 (2023) scan of the spec plus code checks and `rg` patterns for BOLA, BFLA, mass assignment, SSRF | "Security-review our orders API before launch." |
| [api-changelog-deprecation](skills/api-changelog-deprecation/SKILL.md) | Breaking-change rules, changelog format, deprecation timeline, RFC 9745 `Deprecation` / RFC 8594 `Sunset` headers, OpenAPI checks | "Plan the deprecation of GET /v1/orders/{id}/items." |
| [api-docs-writer](skills/api-docs-writer/SKILL.md) | Generates Markdown reference docs with curl examples from OpenAPI, then quickstart, auth, error and recipe guides | "Generate docs with curl examples from our spec." |

## Install

### Claude Code: plugin marketplace (recommended)

Inside Claude Code:

```text
/plugin marketplace add saizul/api-design-skills
/plugin install api-design-skills@api-design-skills
```

Or from your shell:

```bash
claude plugin marketplace add saizul/api-design-skills
claude plugin install api-design-skills@api-design-skills
```

Skills from a plugin are namespaced, for example `/api-design-skills:openapi-review`.
Claude also loads them on its own when your request matches a skill's description.
Update later with `/plugin marketplace update api-design-skills`.

### Claude Code: copy skills manually

Personal skills live in `~/.claude/skills/`, project skills in `.claude/skills/` (commit
them to share with your team):

```bash
git clone https://github.com/saizul/api-design-skills.git
mkdir -p ~/.claude/skills
cp -R api-design-skills/skills/openapi-review ~/.claude/skills/      # one skill
cp -R api-design-skills/skills/* ~/.claude/skills/                   # all of them
```

Each [release](https://github.com/saizul/api-design-skills/releases) also has a zip per
skill and an `api-design-skills-all.zip`.

### OpenAI Codex CLI

Codex reads Agent Skills from `.agents/skills` in your repository (from the current
directory up to the repository root) and from `$HOME/.agents/skills` for personal skills:

```bash
git clone https://github.com/saizul/api-design-skills.git
mkdir -p ~/.agents/skills
cp -R api-design-skills/skills/* ~/.agents/skills/            # personal
# or, inside a project:
mkdir -p .agents/skills && cp -R /path/to/api-design-skills/skills/webhook-design .agents/skills/
```

Restart Codex if a new skill does not show up. Paths and behaviour can change between
Codex releases; check the [Codex skills documentation](https://developers.openai.com/codex/skills)
if this does not work. See also [AGENTS.md](AGENTS.md).

### Other agents

The folders follow the open [Agent Skills specification](https://agentskills.io/specification),
so any agent that supports it can load them. Without skill support, point the agent at a
`SKILL.md` ("follow skills/openapi-review/SKILL.md").

### Requirements for the scripts

Python 3.9 or newer. To read YAML specs: `pip install pyyaml` (JSON specs need nothing).

## Usage examples

You normally just ask; the agent picks the skill and runs its scripts. You can also run
the scripts yourself:

```bash
# Lint a spec (exit 1 on errors; --fail-on warning for stricter CI)
python skills/openapi-review/scripts/openapi_lint.py openapi.yaml

# OWASP API Top 10 scan, only warnings and errors, as JSON
python skills/api-security-review/scripts/api_security_scan.py openapi.yaml --min-severity warning --format json

# Which list endpoints lack pagination or a page size cap?
python skills/pagination-filtering/scripts/pagination_audit.py openapi.yaml

# Do our error responses use application/problem+json? Is this error body valid?
python skills/error-responses/scripts/problem_lint.py spec openapi.yaml
python skills/error-responses/scripts/problem_lint.py doc captured-error.json --status 422

# Debug a webhook signature (secret from an env var, never from argv)
export WEBHOOK_SECRET=...
python skills/webhook-design/scripts/webhook_signature.py verify --scheme github \
  --signature "sha256=..." --body-file body.bin

# Deprecation headers and spec check
python skills/api-changelog-deprecation/scripts/deprecation_headers.py headers \
  --deprecated 2026-03-01 --sunset 2026-09-01 --link https://developer.example.com/migrate
python skills/api-changelog-deprecation/scripts/deprecation_headers.py check openapi.yaml

# Markdown reference with curl examples
python skills/api-docs-writer/scripts/openapi_to_markdown.py openapi.yaml -o docs/api-reference.md
```

Use them as a CI gate:

```yaml
- run: pip install pyyaml
- run: python skills/openapi-review/scripts/openapi_lint.py openapi.yaml --fail-on error
- run: python skills/api-security-review/scripts/api_security_scan.py openapi.yaml --fail-on error
```

## How skills work

1. At start-up the agent reads only each skill's `name` and `description` (a few dozen
   tokens per skill).
2. When your request matches a description, the agent loads that `SKILL.md`: a short,
   step-by-step workflow with decision points and the exact commands to run.
3. Longer material (`references/*.md`, code templates in `assets/`) is read only when a
   step needs it, so context stays small.
4. Scripts give deterministic answers (lint findings, signatures, header values) that the
   agent then explains and acts on.

## FAQ

**Do the scripts send my spec anywhere?** No. They read local files and print to stdout.
No script makes network requests.

**Why Python and not a Node CLI?** Python 3 is on nearly every developer machine and CI
runner, and the standard library covers everything except YAML parsing.

**Can I use only one skill?** Yes. Every skill folder is self-contained (the shared
OpenAPI helpers are copied into each script and a test keeps the copies identical).

**Does it support Swagger 2.0?** The linters expect OpenAPI 3.0 or 3.1. Convert 2.0 specs
first, for example with `swagger2openapi`.

**How is this different from Spectral or Redocly lint?** Those are excellent rule engines
and you can keep using them. These skills add the workflow around them: what to fix first,
how to fix it in your framework, and the design guidance a rule cannot express. The
built-in scripts cover the most common checks with zero setup.

**Is the security scan a pentest?** No. A spec shows only part of the attack surface.
The skill uses the scan as a to-do list and then reviews the code category by category.

## Roadmap

Ideas that would make good contributions (each is a good first issue):

- [ ] `rate-limit-design` skill: RateLimit headers (IETF draft), 429 handling, quotas per plan
- [ ] `api-caching` skill: ETag, `Cache-Control`, conditional requests, CDN rules
- [ ] `graphql-review` skill: schema naming, pagination connections, depth/complexity limits
- [ ] `openapi-review`: rule for `enum` values with mixed casing
- [ ] `openapi-review`: detect duplicate inline schemas that should be `components`
- [ ] `api-docs-writer`: emit Python `requests` and JavaScript `fetch` examples next to curl
- [ ] `webhook-design`: Go and Ruby verification snippets with tests
- [ ] `error-responses`: Spring Boot `ProblemDetail` and ASP.NET Core examples
- [ ] `pagination-filtering`: SQLAlchemy and Prisma keyset examples
- [ ] `api-changelog-deprecation`: generate a changelog draft from two spec versions

## Contributing

Contributions are welcome, from typo fixes to new skills. Read
[CONTRIBUTING.md](CONTRIBUTING.md) for the skill template, the validator and the test
setup, and pick an issue labelled **good first issue**. Please follow the
[Code of Conduct](CODE_OF_CONDUCT.md) and report security problems privately as
described in [SECURITY.md](SECURITY.md).

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
python tools/validate_skills.py && pytest && ruff check . && ruff format --check .
```

## License

[MIT](LICENSE) © Saizul Amin
