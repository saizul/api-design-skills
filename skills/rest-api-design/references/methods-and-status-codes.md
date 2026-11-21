# Methods and status codes

## Methods (RFC 9110)

| Method | Use for | Safe | Idempotent | Typical success |
| --- | --- | --- | --- | --- |
| GET | Read a resource or collection | yes | yes | 200, 304 |
| HEAD | Headers only (existence, size, ETag) | yes | yes | 200 |
| POST | Create in a collection, or run a non-idempotent process | no | no (use `Idempotency-Key`) | 201 + `Location`, 202, 200 |
| PUT | Replace a resource at a client-known URL (create or replace) | no | yes | 200, 204, 201 |
| PATCH | Partial update (`application/merge-patch+json` or `json-patch+json`) | no | not by default | 200, 204 |
| DELETE | Remove a resource | no | yes | 204, 202 |
| OPTIONS | CORS preflight and capabilities | yes | yes | 204 |

Idempotent means repeating the same request leaves the server in the same state; the
response may differ (a second DELETE may return 404).

## Status codes

| Code | When |
| --- | --- |
| 200 OK | Success with a body |
| 201 Created | Resource created; return it and a `Location` header |
| 202 Accepted | Work queued; return a status URL |
| 204 No Content | Success, no body (DELETE, some PUT/PATCH) |
| 304 Not Modified | Conditional GET matched (`If-None-Match` / ETag) |
| 400 Bad Request | Malformed syntax: invalid JSON, wrong types, unknown query parameter |
| 401 Unauthorized | Missing or invalid credentials; send `WWW-Authenticate` |
| 403 Forbidden | Authenticated but not allowed |
| 404 Not Found | Does not exist, or the caller may not know it exists |
| 405 Method Not Allowed | Method not supported; send `Allow` |
| 406 Not Acceptable | Cannot produce the requested `Accept` type |
| 409 Conflict | State conflict: duplicate unique field, version mismatch, idempotency key in flight |
| 410 Gone | Removed on purpose (after a sunset) |
| 412 Precondition Failed | `If-Match` ETag did not match (optimistic locking) |
| 413 Content Too Large | Body exceeds the limit |
| 415 Unsupported Media Type | Wrong `Content-Type` |
| 422 Unprocessable Content | Well-formed but semantically invalid (business validation) |
| 428 Precondition Required | You require `If-Match` and it was missing |
| 429 Too Many Requests | Rate limited; send `Retry-After` |
| 500 Internal Server Error | Unexpected failure; never leak internals |
| 502 / 503 / 504 | Upstream failure, maintenance/overload (`Retry-After`), upstream timeout |

Pick one rule for 400 vs 422 and apply it everywhere. A common rule: 400 when the request
cannot be parsed or fails schema validation, 422 when it parses but breaks a business rule.

## Useful headers

- `Location` on 201 and 202.
- `ETag` + `If-None-Match` (caching) and `If-Match` (lost-update protection).
- `Retry-After` on 429 and 503.
- `RateLimit-Policy` / `RateLimit` (IETF httpapi draft) or the common `X-RateLimit-*` trio.
- `Cache-Control: no-store` on responses with personal data.
- `Deprecation`, `Sunset`, `Link` for deprecated endpoints (see `api-changelog-deprecation`).
