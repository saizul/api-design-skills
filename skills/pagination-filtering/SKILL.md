---
name: pagination-filtering
description: Design and implement pagination, filtering and sorting for HTTP API list endpoints - cursor (keyset) vs offset vs page-number trade-offs, page size limits, opaque signed cursors, RFC 8288 Link headers, filter and sort parameter conventions and the matching SQL. Use when the user builds or reviews a list/search/collection endpoint, sees slow deep pages or duplicated/skipped items, or asks how to paginate an API. Includes an OpenAPI audit script and a tested cursor implementation.
license: MIT
compatibility: Python 3.9+. YAML specs need PyYAML.
metadata:
  author: Saizul Amin
  version: "0.1.0"
---

# Pagination, filtering and sorting

Paths such as `scripts/...` and `references/...` are relative to this skill's folder (`${CLAUDE_SKILL_DIR}` in Claude Code). Run scripts from the user's project with that folder's path.

## When to use

- Adding or reviewing any endpoint that returns a list.
- Users report missing or duplicate items while paging, or deep pages are slow.
- Standardising list conventions across an API.

## When not to use

- Streaming exports of whole datasets: offer an async export job or NDJSON stream.
- GraphQL connections: follow the Relay cursor connection spec instead.

## Workflow

1. **Audit existing endpoints** (if there is a spec):

   ```bash
   python scripts/pagination_audit.py openapi.yaml
   python scripts/pagination_audit.py openapi.yaml --format json --fail-on never
   ```

   It flags list endpoints without pagination, uncapped page sizes, bare arrays, missing
   next links, offset pagination and mixed parameter names.
2. **Choose the style** with the decision table in
   [references/strategies.md](references/strategies.md). Default to **cursor (keyset)**
   for anything that grows or changes; page numbers only for small, stable, admin-style
   lists that need "jump to page N".
3. **Fix the contract** (same names on every endpoint):
   - `limit` (default 20, maximum 100; values above the maximum are clamped, values below
     1 are a 400).
   - `cursor` (opaque string from the previous response).
   - Response envelope: `{"data": [...], "next_cursor": "...", "has_more": true}` and,
     optionally, a `Link: <...>; rel="next"` header (RFC 8288).
   - Filters: `?status=active&created_after=2026-01-01T00:00:00Z`; multiple values with a
     repeated parameter or comma list (pick one); sort with `sort=-created_at,id`.
4. **Implement** with [assets/cursor_pagination.py](assets/cursor_pagination.py) (signed
   cursors, `clamp_limit`, `paginate`, `link_header`) and the SQL patterns in
   [references/strategies.md](references/strategies.md#keyset-sql). The sort must be
   total: always add the primary key as the last sort column.
5. **Index** the sort columns (`CREATE INDEX ... ON orders (customer_id, created_at DESC, id DESC)`).
6. **Allowlist** filter and sort fields; never interpolate them into SQL.
7. **Test**: first page, middle page, last page (`has_more: false`, no `next_cursor`), a
   row inserted between page fetches does not cause a duplicate, a tampered cursor returns
   400, `limit=1000` is clamped.

## Output

1. The chosen style and why (one paragraph).
2. The parameter and response contract (OpenAPI snippet).
3. Query/handler code for the user's stack, plus the index.
4. Audit results before/after when a spec exists.

## Example prompts

- "Our /orders endpoint uses offset and gets slow after page 500. Fix it."
- "Design filtering and sorting for a products search endpoint."
- "Check our spec: which list endpoints are missing pagination?"
