# RFC 9457 problem details

RFC 9457 (July 2023) obsoletes RFC 7807. Media types: `application/problem+json` and
`application/problem+xml`.

## Members

| Member | Type | Meaning |
| --- | --- | --- |
| `type` | URI reference | Identifies the problem type. Defaults to `about:blank`. Should resolve to human docs when dereferenced, but clients must not need to fetch it. |
| `status` | number | The HTTP status code, advisory (must match the real status). |
| `title` | string | Short summary of the type; should not change between occurrences (except localisation). With `about:blank`, use the HTTP reason phrase. |
| `detail` | string | Explanation of this occurrence, for humans; clients should not parse it. |
| `instance` | URI reference | Identifies this occurrence (for example `urn:uuid:...` or `/errors/abc123`). |

Extension members are allowed. RFC 9457 recommends names that start with a letter and
contain only letters, digits and underscores, at least three characters long, so they
work in many languages. Clients must ignore extensions they do not understand.

RFC 9457 also defines a registry of common problem types (IANA "HTTP Problem Types").
Check it before inventing a type for a generic situation.

## Example catalog

| type | title | status | Extensions |
| --- | --- | --- | --- |
| `about:blank` | (reason phrase) | 400/401/403/404/405/415 | - |
| `https://api.example.com/problems/validation-error` | Your request is not valid. | 422 | `errors[]` with `detail`, `pointer` or `parameter` |
| `https://api.example.com/problems/conflict` | The resource was modified. | 409/412 | `current_version` |
| `https://api.example.com/problems/insufficient-funds` | Insufficient funds. | 422 | `balance`, `currency` |
| `https://api.example.com/problems/rate-limited` | Too many requests. | 429 | `retry_after` (plus `Retry-After` header) |
| `https://api.example.com/problems/idempotency-key-reused` | Idempotency key reused. | 422 | - |
| `https://api.example.com/problems/internal` | Something went wrong on our side. | 500 | - (only `instance`) |

## Examples

Validation (one response, many errors):

```json
{
  "type": "https://api.example.com/problems/validation-error",
  "title": "Your request is not valid.",
  "status": 422,
  "detail": "2 fields are invalid.",
  "instance": "urn:uuid:5b1f3f4e-8a5c-4c3e-9b7d-3a1f2e4d5c6b",
  "errors": [
    {"detail": "must be a valid email address", "pointer": "#/email"},
    {"detail": "must be at least 1", "pointer": "#/items/0/quantity"}
  ]
}
```

Business rule:

```json
{
  "type": "https://api.example.com/problems/insufficient-funds",
  "title": "Insufficient funds.",
  "status": 422,
  "detail": "The balance of account 12345 is 30.00 USD; the payment needs 50.00 USD.",
  "balance": 3000,
  "currency": "USD"
}
```

Unexpected failure (log the stack trace, return only this):

```json
{
  "type": "about:blank",
  "title": "Internal Server Error",
  "status": 500,
  "instance": "urn:uuid:0f8c7e7a-2c1b-4c47-9a0d-b1f6c1d2e3f4"
}
```

## Client guidance to publish

- Branch on `type` (and `status`), never on `title` or `detail`.
- Treat an unknown `type` like `about:blank` for its status code.
- Show `detail` to developers, not necessarily end users.
- Quote `instance` when contacting support.
