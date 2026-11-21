# Webhook design reference

## Envelope

```json
{
  "id": "evt_01JH2Y8Q3V5K7R9T1W3Y5A7C9E",
  "type": "invoice.paid",
  "created_at": "2026-01-15T09:30:00Z",
  "api_version": "2026-01-01",
  "data": {
    "object": {"id": "in_123", "status": "paid", "amount_due": 5000, "currency": "usd"}
  }
}
```

- `id` is unique per event and stays the same on every retry.
- `type` is `resource.verb` in the past tense: `customer.created`, `invoice.payment_failed`.
- Thin events (`data.id` only) force a fetch but are always fresh and smaller; fat events
  save a round trip but can be stale when processed late.

## Signing schemes

| Scheme | Headers | Signed content | Encoding |
| --- | --- | --- | --- |
| Standard Webhooks | `webhook-id`, `webhook-timestamp`, `webhook-signature: v1,<sig>` (space-separated list) | `{id}.{timestamp}.{raw body}` | base64 HMAC-SHA256; secret `whsec_` + base64 key |
| GitHub | `X-Hub-Signature-256: sha256=<hex>` | raw body | hex HMAC-SHA256 |
| Stripe | `Stripe-Signature: t=<ts>,v1=<hex>[,v1=...]` | `{t}.{raw body}` | hex HMAC-SHA256 |

Always: HMAC-SHA256, constant-time comparison, timestamp tolerance (300 s), per-endpoint
secrets of at least 32 random bytes, and secret rotation with an overlap period. Ed25519
signatures (Standard Webhooks `v1a`) let consumers verify without holding a shared secret.

Test vectors used in this repository's tests:

- GitHub docs: secret `It's a Secret to Everybody`, body `Hello, World!` gives
  `sha256=757107ea0eb2509fc211221cce984b8a37570b6d7586c22c46f4379c8b043e17`.
- Standard Webhooks reference libraries: message id `msg_p5jXN8AQM9LWM0D4loKWxJek`,
  timestamp `1614265330`, body `{"test": 2432232314}` with the libraries' published test
  secret give `v1,g0hM9SsE+OTPJTGt/tmIKtSyZlE3uFJELVlNIOLJ1OE=`.

## Retry schedule (example)

Immediately, then 5 s, 5 min, 30 min, 2 h, 5 h, 10 h, 10 h (about 28 hours in total),
each with +/-20% jitter. Some providers retry for 3 days. Stop on 2xx. Stop early and do
not retry on 410 Gone (treat as unsubscribe). Respect `Retry-After` on 429/503.

After N consecutive days of failure, disable the endpoint and email the owner.

## Consumer checklist

- [ ] Raw body captured before parsing (Express `express.raw()`, FastAPI `await request.body()`,
      PHP `file_get_contents('php://input')`, Laravel `$request->getContent()`).
- [ ] Signature verified with constant-time compare; timestamp within tolerance.
- [ ] Endpoint secret loaded from a secret store, not source code.
- [ ] Event ID stored with a unique constraint; duplicates return 200 without reprocessing.
- [ ] Work is queued; the endpoint responds within a few seconds.
- [ ] Unknown event types are acknowledged (2xx) and ignored, not 4xx.
- [ ] Out-of-order events cannot overwrite newer state.
- [ ] Endpoint is HTTPS and rejects other methods than POST.

## Why verification fails

1. The body was parsed and re-serialised (whitespace, key order, unicode escapes change).
2. A framework or proxy changed the body (decompression, charset conversion, trailing newline).
3. Wrong secret: test vs live mode, an old secret after rotation, or the `whsec_` prefix
   handled wrongly (Standard Webhooks base64-decodes the part after the prefix; Stripe
   uses the full string as the key).
4. Comparing hex to base64, or uppercase to lowercase hex.
5. Clock skew larger than the tolerance (check NTP).
6. Header parsing: multiple signatures in one header must each be tried.

## Provider security

- Validate destination URLs: HTTPS only in production; resolve DNS and block private
  (RFC 1918), loopback, link-local (169.254.0.0/16, including cloud metadata) and IPv6
  equivalents on every attempt; disable redirects.
- Do not include secrets or full card/PII data in payloads unless required.
- Rate-limit deliveries per endpoint so a slow consumer does not starve others.
