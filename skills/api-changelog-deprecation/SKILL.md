---
name: api-changelog-deprecation
description: Plan and communicate API changes - classify breaking vs non-breaking changes, write an API changelog entry, run a deprecation timeline, and emit Deprecation (RFC 9745), Sunset (RFC 8594) and Link headers, with OpenAPI deprecated/x-sunset annotations and 410 Gone after removal. Use when the user is removing or renaming an endpoint or field, retiring an API version, writing API release notes, or asks how to deprecate something without breaking clients. Includes a header generator and an OpenAPI deprecation checker.
license: MIT
compatibility: Python 3.9+. YAML specs need PyYAML.
metadata:
  author: Saizul Amin
  version: "0.1.0"
---

# API changelog and deprecation

Paths such as `scripts/...` and `references/...` are relative to this skill's folder (`${CLAUDE_SKILL_DIR}` in Claude Code). Run scripts from the user's project with that folder's path.

## When to use

- Removing, renaming or changing the behaviour of an endpoint, parameter or field.
- Retiring an API version (`/v1` after `/v2` ships).
- Writing API release notes or a public changelog.

## When not to use

- Library/package changelogs: use Keep a Changelog and SemVer directly.
- Internal-only APIs with a single consumer you deploy together (just coordinate the change).

## Workflow

1. **Classify the change** with the breaking-change list in
   [references/changelog-format.md](references/changelog-format.md#breaking-or-not).
   Non-breaking: ship and log it. Breaking: plan a deprecation or a new version.
2. **Set the timeline.** Announce, then deprecate (`deprecated: true` in OpenAPI and
   headers on responses), then sunset. Public APIs: at least 6 months between
   deprecation and sunset; partner APIs: 3 months; tell clients the exact date.
3. **Emit headers on every response** from the deprecated endpoint:

   ```bash
   python scripts/deprecation_headers.py headers --deprecated 2026-03-01 \
     --sunset 2026-09-01 --link https://developer.example.com/migrate/orders-v2
   # Deprecation: @1772323200
   # Sunset: Tue, 01 Sep 2026 00:00:00 GMT
   # Link: <https://developer.example.com/migrate/orders-v2>; rel="deprecation"; type="text/html"
   python scripts/deprecation_headers.py headers ... --format nginx   # add_header lines
   ```

   `Deprecation` is an RFC 9745 structured-field date (`@` + Unix seconds). `Sunset` is an
   RFC 8594 HTTP-date. Sunset must not be earlier than deprecation.
4. **Annotate the spec**: `deprecated: true`, a description that names the replacement,
   `x-sunset: 2026-09-01`, and the `Deprecation`/`Sunset` response headers. Check it:

   ```bash
   python scripts/deprecation_headers.py check openapi.yaml
   ```

   Exit 1 on warnings (missing replacement or sunset date, `x-sunset` on an operation that
   is not `deprecated: true`) or errors (sunset in the past). `sunset-soon` (info) lists
   operations whose sunset is within `--soon-days` (default 30): time for the last reminder.
5. **Measure and notify.** Log calls to deprecated endpoints per client (API key/account),
   email the owners of active clients at announcement, 30 days and 7 days before sunset.
   Consider short "brownouts" (scheduled temporary 410s) before the final removal.
6. **After sunset** return `410 Gone` with a problem body that links to the migration
   guide, for at least a few months, then remove the route.
7. **Write the changelog entry** in the format in
   [references/changelog-format.md](references/changelog-format.md).

## Output

1. Change classification (breaking or not, and why).
2. Timeline with dates (announce, deprecate, brownouts, sunset, removal).
3. Header values / middleware snippet, OpenAPI annotations, and the 410 response.
4. Changelog entry and the customer notice text.

## Example prompts

- "We are replacing GET /v1/orders/{id}/items with an `items` field. Plan the deprecation."
- "Write the changelog for this API release from these PRs."
- "What headers should a deprecated endpoint return?"
