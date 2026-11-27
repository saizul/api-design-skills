# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- `api-changelog-deprecation`: `deprecation_headers.py check` reports `sunset-soon` (info) for
  deprecated operations whose `x-sunset` is within `--soon-days` (default 30, `0` turns it
  off) and `sunset-not-deprecated` (warning) for operations with `x-sunset` that are not
  marked `deprecated: true`.

### Added

- `openapi-review`: `enum-casing` rule (warning) for enums whose values mix casing styles,
  such as `[pending, PAID, inReview]`, in component schemas (including nested properties,
  array items and `allOf`/`oneOf`/`anyOf`) and inline parameter schemas.

## [0.1.0] - 2026-11-21

### Added

- `rest-api-design`: resource naming, methods, status codes, versioning and a
  release checklist.
- `openapi-review`: `openapi_lint.py`, 24 rules for missing descriptions, operationIds,
  error responses, examples, security, undeclared path parameters and naming.
- `error-responses`: RFC 9457 problem details catalog, handlers for Express, FastAPI,
  Flask, Laravel and plain PHP, OpenAPI components and `problem_lint.py`.
- `pagination-filtering`: cursor vs offset guide, keyset SQL, `pagination_audit.py` and a
  tested signed-cursor and RFC 8288 Link header implementation.
- `webhook-design`: provider and consumer workflows, `webhook_signature.py` (Standard
  Webhooks, GitHub, Stripe, plain HMAC) and verification snippets for Node.js and PHP,
  tested against published vectors.
- `idempotency-keys`: Idempotency-Key contract, storage schemas and a tested SQLite
  reference implementation.
- `api-security-review`: `api_security_scan.py` mapped to the OWASP API Security Top 10
  (2023) plus code-review checks and `rg` patterns per category.
- `api-changelog-deprecation`: changelog format, deprecation timeline and
  `deprecation_headers.py` for RFC 9745 Deprecation, RFC 8594 Sunset and Link headers.
- `api-docs-writer`: `openapi_to_markdown.py` (Markdown reference with curl examples) and
  guide templates.
- Claude Code plugin marketplace manifest, `tools/validate_skills.py`, CI on Python
  3.11-3.13 and release zips per skill.

[Unreleased]: https://github.com/saizul/api-design-skills/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/saizul/api-design-skills/releases/tag/v0.1.0
