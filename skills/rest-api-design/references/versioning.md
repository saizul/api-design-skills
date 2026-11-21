# Versioning and compatibility

## Strategies

| Strategy | Example | Pros | Cons |
| --- | --- | --- | --- |
| URL major version | `/v1/orders` | Visible, cache-friendly, easy routing and docs | Whole-API bumps |
| Header / media type | `Accept: application/vnd.acme.v2+json` | Clean URLs, per-resource versions | Hidden, harder to test with a browser or curl |
| Date-based header | `Api-Version: 2026-01-15` | Fine-grained, per-account pinning | Needs a version-transform layer |
| Query parameter | `?version=2` | Easy | Easy to forget, pollutes caches |

Default: URL major version for public APIs. Date-based versions suit large APIs that ship
breaking changes often and can afford compatibility transforms.

## Non-breaking (no new version)

- Adding an endpoint, an optional request field, a response field, an optional query
  parameter, a new enum value **only if clients were told to tolerate unknown values**.
- Relaxing validation (longer max length, optional instead of required).

## Breaking (new version or a deprecation cycle)

- Removing or renaming a field, endpoint, parameter or enum value.
- Changing a type, format, default, status code or error `type`.
- Making an optional field required; tightening validation.
- Changing auth requirements or pagination style.

## Rules for clients (put these in your docs)

- Ignore unknown fields; treat unknown enum values as "other".
- Do not depend on field order or undocumented fields.
- Follow `Link rel="next"` / `next_cursor` instead of building page URLs.
