# REST API review checklist

Mark each item Pass / Fail / N/A. "Must" items block release.

## URLs and resources
- [ ] (must) Plural nouns, lowercase kebab-case segments, no verbs: `/v1/payment-methods`
- [ ] (must) Identifiers are path segments: `/orders/{order_id}`
- [ ] (should) At most one level of nesting; deeper relations use filters
- [ ] (should) No trailing slashes or file extensions
- [ ] (should) Non-CRUD actions modelled as sub-resources or state changes

## Methods and status codes
- [ ] (must) GET/HEAD never change state
- [ ] (must) POST that creates returns 201 with `Location` and the created resource
- [ ] (must) Errors use 4xx for client problems and 5xx only for server faults
- [ ] (must) 401 vs 403 vs 404 applied consistently; private resources return 404
- [ ] (should) 409 for state conflicts, 412 for failed `If-Match`, 429 with `Retry-After`
- [ ] (should) Long work returns 202 + status resource

## Payloads
- [ ] (must) One field casing style across the API
- [ ] (must) Timestamps are ISO 8601 / RFC 3339 in UTC (`2026-01-15T09:30:00Z`)
- [ ] (must) Money is integer minor units plus ISO 4217 currency, never floats
- [ ] (should) IDs are strings (allows UUIDs/prefixed IDs later)
- [ ] (should) Collections are wrapped (`{"data": [...]}`), not bare arrays
- [ ] (should) Booleans are not tri-state; nullable fields are documented
- [ ] (should) Enums are lowercase strings and documented as extensible

## Errors, lists and retries
- [ ] (must) Errors use RFC 9457 `application/problem+json` with a stable `type`
- [ ] (must) Every list endpoint is paginated with a capped page size
- [ ] (should) Creating POSTs with side effects accept `Idempotency-Key`
- [ ] (should) Filters and sort fields are allowlisted and documented

## Security
- [ ] (must) Every endpoint requires auth unless explicitly public
- [ ] (must) Object-level authorization on every `{id}` route (owner or tenant check)
- [ ] (must) HTTPS only; no credentials in query strings
- [ ] (should) Rate limits documented; request size limits enforced
- [ ] (should) Responses never include secrets, password hashes or internal IDs that grant access

## Evolution
- [ ] (must) Versioning strategy chosen and documented
- [ ] (must) Breaking changes listed with a migration path and deprecation dates
- [ ] (should) Clients told to ignore unknown fields and enum values
