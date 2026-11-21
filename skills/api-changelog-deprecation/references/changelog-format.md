# API changelog format and deprecation reference

## Breaking or not

Breaking (needs deprecation or a new version):

- Removing or renaming an endpoint, field, parameter, header or enum value.
- Changing a field type, format, unit, default value or nullability.
- Making an optional input required, tightening validation, lowering limits.
- Changing status codes, error `type` URIs, pagination style or sort order defaults.
- Changing authentication, required scopes or rate limits downward.

Usually non-breaking (document anyway):

- New endpoints, new optional parameters, new response fields, new event types.
- New enum values, if clients were told to handle unknown values.
- Relaxed validation, higher limits, performance changes.

## Changelog entry

One entry per release date, newest first, sections in this order. Each item names the
endpoint or field, says what changed and what clients must do.

```markdown
## 2026-03-01

### Breaking
- `GET /v1/orders/{id}/items` is deprecated and will be removed on **2026-09-01**.
  Use the `items` field on `GET /v1/orders/{id}` instead. [Migration guide](https://developer.example.com/migrate/orders-v2)

### Added
- `POST /v1/refunds` accepts an optional `reason` (`duplicate`, `fraudulent`, `requested_by_customer`).
- Webhook event `refund.updated`.

### Changed
- `limit` on list endpoints now allows up to 200 (was 100).

### Deprecated
- Response field `order.total_price` (string). Use `order.total` (integer minor units). Sunset 2026-09-01.

### Fixed
- `GET /v1/customers` no longer returns deleted customers when `include_deleted` is omitted.

### Security
- Access tokens now expire after 1 hour (was 24 hours).
```

Keep a machine-readable copy if clients ask for it (for example `changelog.json` with
`date`, `type`, `endpoints`, `summary`, `sunset`).

## Headers

```
Deprecation: @1772323200
Sunset: Tue, 01 Sep 2026 00:00:00 GMT
Link: <https://developer.example.com/migrate/orders-v2>; rel="deprecation"; type="text/html"
```

- RFC 9745 (March 2025) `Deprecation`: an Item Structured Header whose value is a Date
  (`@` followed by Unix seconds). The date may be in the past (already deprecated) or the
  future (will be deprecated). A `Link` with `rel="deprecation"` points to human docs.
- RFC 8594 `Sunset`: HTTP-date after which the resource is expected to stop responding.
  `rel="sunset"` links to the sunset policy.
- Sunset should not be earlier than Deprecation.
- Add the headers to all responses of the deprecated resource, including errors.

## OpenAPI annotations

```yaml
/v1/orders/{id}/items:
  get:
    deprecated: true
    x-sunset: "2026-09-01"
    summary: List order items (deprecated)
    description: Deprecated on 2026-03-01. Use the `items` field of GET /v1/orders/{id} instead.
    responses:
      "200":
        description: Items
        headers:
          Deprecation:
            description: RFC 9745 deprecation date
            schema: { type: string, example: "@1772323200" }
          Sunset:
            description: RFC 8594 removal date
            schema: { type: string, example: "Tue, 01 Sep 2026 00:00:00 GMT" }
```

## After sunset

```http
HTTP/1.1 410 Gone
Content-Type: application/problem+json

{"type": "https://api.example.com/problems/endpoint-removed",
 "title": "This endpoint has been removed.",
 "status": 410,
 "detail": "GET /v1/orders/{id}/items was removed on 2026-09-01. Use GET /v1/orders/{id}.",
 "migration_guide": "https://developer.example.com/migrate/orders-v2"}
```

## Customer notice template

> **Action required by 2026-09-01:** `GET /v1/orders/{id}/items` will stop working on
> 1 September 2026. Your account made 1,240 calls to it in the last 30 days. Switch to the
> `items` field on `GET /v1/orders/{id}` (guide: ...). Responses already carry
> `Deprecation` and `Sunset` headers so you can detect affected calls in your logs.
