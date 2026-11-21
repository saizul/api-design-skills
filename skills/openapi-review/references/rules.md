# Lint rules

| Rule | Severity | Why it matters | Typical fix |
| --- | --- | --- | --- |
| `spec-version` | error | Tools behave differently on 2.0 and 3.x | Convert to `openapi: 3.1.0` or `3.0.3` |
| `info-title`, `info-version` | error | Required by the spec | Add them |
| `info-description` | warning | First thing readers see | One paragraph: what the API does, who it is for, auth summary |
| `servers` | info | Docs and tools need a base URL | `servers: [{url: https://api.example.com/v1}]` |
| `operation-id` | error | SDK generators and docs need method names | `operationId: listOrders` |
| `operation-id-unique` | error | Duplicate names break generators | Rename one |
| `operation-id-style` | warning | Mixed styles produce odd SDK method names | Use one style (camelCase is most common) |
| `operation-summary` | warning | Index pages show the summary | Short verb phrase: "List orders" |
| `operation-tags` | info | Docs group endpoints by tag | Tag by resource |
| `success-response` | error | Clients do not know what success looks like | Document 200/201/204 |
| `error-responses` | warning | Clients cannot handle failures | Reference shared `components.responses` (400, 401, 404, 422, 429) |
| `response-description` | error | Required by the spec | Add a description |
| `parameter-description` | warning | Readers guess the meaning | Describe format, default and limits |
| `path-parameter-declared` | error | Spec is invalid; generators fail | Add `in: path` parameter |
| `path-parameter-required` | error | Path params must be `required: true` | Set it |
| `get-request-body` | warning | Bodies on GET/DELETE are dropped by many proxies and clients | Use query parameters |
| `examples` | warning | Examples are what developers copy | Add `example` on the media type or schema |
| `security-schemes` | warning | Nobody knows how to authenticate | Declare schemes in `components.securitySchemes` |
| `operation-security` | warning | Unclear whether the endpoint is public | Set global `security`, or `security: []` for public endpoints |
| `path-casing` | warning | Inconsistent URLs | lowercase kebab-case segments |
| `path-trailing-slash` | warning | `/a` and `/a/` may route differently | Remove the slash |
| `path-verb` | warning | Actions in URLs hide the resource model | Model as a resource or state change |
| `property-casing` | warning | Mixed snake_case/camelCase confuses clients | Pick one |

Ignore a rule with `--ignore RULE` (repeatable) and say why in the PR.

## Manual review

The linter checks structure. Also review:

- [ ] Summaries describe the business action, not the implementation ("Refund a payment",
      not "Calls refund service").
- [ ] Examples are realistic (real-looking IDs, timestamps, amounts) and consistent between
      request and response.
- [ ] Errors share one schema (RFC 9457 problem details) and document stable `type` URIs.
- [ ] Every list endpoint documents pagination and the maximum page size.
- [ ] Required vs optional fields match the implementation; `nullable`/`type: [x, "null"]`
      is used deliberately.
- [ ] `readOnly` on server-generated fields (`id`, `created_at`), `writeOnly` on secrets.
- [ ] Enums are documented as extensible if new values may appear.
- [ ] OAuth scopes are listed per operation and match what the code enforces.
- [ ] Deprecated operations say what replaces them and when they sunset.
