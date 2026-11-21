---
name: rest-api-design
description: Design or review REST/HTTP API endpoints - resource naming, URL structure, HTTP methods, status codes, headers, versioning, request/response shapes and consistency. Use when the user is creating new endpoints, sketching an API, choosing status codes or methods, deciding on versioning, or asks "is this a good API design?". Produces an endpoint table and a checklist-based review.
license: MIT
metadata:
  author: Saizul Amin
  version: "0.1.0"
---

# REST API design

Turn a feature description or an existing set of routes into a consistent,
predictable HTTP API, and review designs against a checklist.

## When to use

- Designing new endpoints or a new API from a feature description or data model.
- Reviewing route definitions (Express, FastAPI, Laravel, Rails, Spring, Go) or an API sketch.
- Choosing between methods, status codes, URL shapes or versioning strategies.

## When not to use

- GraphQL or gRPC schemas (different conventions).
- Linting an existing OpenAPI file in detail: use `openapi-review`.
- Error body format only: use `error-responses`. Pagination only: use `pagination-filtering`.

## Workflow

1. **Collect the resources.** List the nouns in the domain and their relationships
   (owns, belongs to, many-to-many). Ask about the consumers (public, partner, internal,
   mobile) because that decides versioning and compatibility rules.
2. **Name the URLs.** Plural nouns, lowercase kebab-case, at most one level of nesting
   for ownership, identifiers as path segments:
   `/v1/customers/{customer_id}/orders`. No verbs, no file extensions, no trailing slash.
3. **Map operations to methods** using the table in
   [references/methods-and-status-codes.md](references/methods-and-status-codes.md).
   Actions that are not CRUD become sub-resources or state changes:
   `POST /orders/{id}/cancellation` or `PATCH /orders/{id} {"status": "cancelled"}`,
   not `POST /cancelOrder`.
4. **Pick status codes** for every outcome (success, validation, auth, not found,
   conflict, rate limit). Use 201 + `Location` for creation, 202 for async work, 204 for
   empty success, 409 for state conflicts, 422 for semantic validation errors.
5. **Shape the payloads.** One casing style for fields (pick `snake_case` or `camelCase`
   and never mix), ISO 8601 UTC timestamps, string IDs, money as integer minor units plus
   currency, enums as lowercase strings, envelopes for collections (`{"data": [...],
   "next_cursor": ...}`).
6. **Decide versioning and evolution** with
   [references/versioning.md](references/versioning.md): URL major version (`/v1`) by
   default; additive changes never bump it; breaking changes need a new version plus a
   deprecation window (`api-changelog-deprecation`).
7. **Cross-cutting concerns:** auth on every endpoint, idempotency for POSTs that create
   money-moving or external side effects (`idempotency-keys`), pagination on every list
   (`pagination-filtering`), RFC 9457 errors (`error-responses`), rate limit headers.
8. **Run the checklist** in [references/checklist.md](references/checklist.md) and fix
   every "must" item before presenting the design.

## Decision points

- Nested vs flat: nest only when the child cannot exist without the parent and the
  parent ID is always known. Otherwise use a flat resource with a filter
  (`/orders?customer_id=...`).
- PUT vs PATCH: PUT replaces the whole representation (client sends everything); PATCH
  with `application/merge-patch+json` (RFC 7396) for partial updates. Prefer PATCH for
  public APIs.
- 404 vs 403 for resources the caller may not see: return 404 to avoid confirming that
  the resource exists.
- Sync vs async: if work can exceed a few seconds, return `202 Accepted` with a status
  resource (`Location: /v1/jobs/{id}`).

## Output

1. An endpoint table: `Method | Path | Purpose | Success | Errors | Auth/scope | Idempotent`.
2. Example request and response for each non-trivial endpoint.
3. A review list grouped as **Must fix / Should fix / Consider**, each item naming the
   endpoint and the concrete change.
4. Optional: an OpenAPI 3.1 skeleton when the user asks for one.

## Example prompts

- "Design endpoints for a subscription billing feature: plans, subscriptions, invoices."
- "Review these Express routes for REST conventions."
- "Should cancelling an order be DELETE or POST?"
