# Documentation templates

## Quickstart

```markdown
# Quickstart

Make your first API call in about five minutes.

## 1. Get an API key
Create a key in **Dashboard > Developers > API keys**. Test keys work only against the
sandbox (`https://sandbox.example.com`). Store the key in an environment variable:

    export API_TOKEN=...   # paste your test key

## 2. Make a request

    curl https://sandbox.example.com/v1/orders?limit=1 \
      -H "Authorization: Bearer $API_TOKEN"

## 3. Read the response

    {"data": [{"id": "ord_123", "status": "paid"}], "next_cursor": null, "has_more": false}

`data` holds the results. See [Pagination](pagination.md) to fetch more.

## Next steps
- [Create your first order](recipes/create-order.md)
- [Handle errors](errors.md)
- [Receive webhooks](webhooks.md)
```

## Authentication guide

Cover: where to get credentials, test vs live, how to send them (header example), token
lifetime and refresh, scopes per endpoint group, rotating keys without downtime, and what
401 vs 403 mean. Never show a real key; use `$API_TOKEN`.

## Errors guide

```markdown
# Errors

Errors use [RFC 9457](https://www.rfc-editor.org/rfc/rfc9457) problem details with
`Content-Type: application/problem+json`. Branch on `type`, not on `title` or `detail`.

| type | status | What to do |
| --- | --- | --- |
| `https://api.example.com/problems/validation-error` | 422 | Fix the fields listed in `errors[]` |
| `about:blank` (401) | 401 | Check the API key |
| `https://api.example.com/problems/rate-limited` | 429 | Wait `Retry-After` seconds and retry |
```

## Recipe

```markdown
# Create an order and take payment

You will: create a customer, create an order, pay it, and confirm the webhook.

1. Create the customer (save `id`) ...
2. Create the order with that customer (send an `Idempotency-Key`) ...
3. ...

Full script: [create-order.sh](create-order.sh)
```

## Reference page conventions

- One section per tag, one subsection per operation: summary, method + path,
  description, parameters table, request body table, curl example, responses table,
  example response.
- Mark deprecated operations at the top of their section with the replacement.
- Link shared concepts (pagination, errors) instead of repeating them per endpoint.
