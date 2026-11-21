# Pagination strategies

| | Cursor / keyset | Offset (`limit` + `offset`) | Page number (`page` + `per_page`) |
| --- | --- | --- | --- |
| Deep page cost | Constant (index seek) | Grows with offset (scans and discards rows) | Same as offset |
| Inserts/deletes while paging | Stable: no duplicates or gaps | Duplicates or skipped rows | Duplicates or skipped rows |
| Jump to page N | No | Yes | Yes |
| Total count | Optional, separate | Often expected (costly `COUNT(*)`) | Usually expected |
| Best for | Feeds, large/growing tables, public APIs, sync | Small admin tables | UIs with numbered pages on small data |

Recommendation: cursor pagination by default. If a UI needs totals, return an
approximate count or a separate `/count` endpoint rather than counting on every page.

## Contract

Request:

```
GET /v1/orders?status=paid&sort=-created_at&limit=50&cursor=eyJ2IjoxLC...
```

Response:

```json
{
  "data": [{"id": "ord_123", "created_at": "2026-01-15T09:30:00Z", "status": "paid"}],
  "next_cursor": "eyJ2IjoxLCJzIjoiLWNyZWF0ZWRfYXQiLCJwIjp7Li4ufX0.mJ2...",
  "has_more": true
}
```

Optional header (RFC 8288):

```
Link: <https://api.example.com/v1/orders?status=paid&sort=-created_at&limit=50&cursor=eyJ2...>; rel="next"
```

Rules:

- Cursors are opaque. Clients must not build or parse them. Sign them (HMAC) so they cannot
  be forged, and bind them to the sort order; reject mismatches with 400.
- Filters and sort must be resent with the cursor (or embedded in it). Reject a cursor
  used with different filters if you embed them.
- `next_cursor` is `null` and `has_more` is `false` on the last page.
- Cursors may expire; document it and return 400 with a problem `type` such as
  `https://api.example.com/problems/invalid-cursor`.

## Keyset SQL

Sort `created_at DESC, id DESC` (id breaks ties so the order is total):

```sql
-- first page
SELECT id, created_at, status FROM orders
WHERE customer_id = :customer_id
ORDER BY created_at DESC, id DESC
LIMIT :limit_plus_one;

-- next pages: position from the cursor = last row of the previous page
SELECT id, created_at, status FROM orders
WHERE customer_id = :customer_id
  AND (created_at, id) < (:cursor_created_at, :cursor_id)   -- row values: PostgreSQL, MySQL 8, SQLite 3.15+
ORDER BY created_at DESC, id DESC
LIMIT :limit_plus_one;

CREATE INDEX orders_customer_created_id ON orders (customer_id, created_at DESC, id DESC);
```

Without row-value comparison: `created_at < :c OR (created_at = :c AND id < :id)`.
For ascending order flip `<` to `>`. Fetch `limit + 1` rows: if you get the extra row,
there is another page; drop it from the response.

Mixed directions (`sort=-created_at,name`) cannot use a single row comparison; expand to
the OR form per column, or restrict sorts to a few supported combinations with matching
indexes.

## Filtering conventions

| Need | Convention |
| --- | --- |
| Equality | `?status=paid` |
| Several values | `?status=paid,refunded` or `?status=paid&status=refunded` (pick one API-wide) |
| Ranges | `?created_after=...&created_before=...` or `?amount[gte]=100` |
| Text search | `?q=blue+shirt` (document which fields are searched) |
| Sort | `?sort=-created_at,id` (`-` = descending) |
| Sparse fields | `?fields=id,status` |

- Allowlist filterable and sortable fields; return 400 for unknown ones (silently ignoring
  a misspelt filter returns wrong data).
- Validate types and formats (dates, enums) before building the query.
- Bound result cost: maximum `limit`, maximum number of filter values, timeouts.
- Prefer range filters on timestamps over offset for "everything since" sync use cases:
  `?updated_after=<last seen>&sort=updated_at,id` with a cursor.
