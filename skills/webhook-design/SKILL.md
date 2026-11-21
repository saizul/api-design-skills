---
name: webhook-design
description: Design, send and receive webhooks safely - event naming and payload envelope, HMAC signatures (Standard Webhooks, GitHub, Stripe styles), timestamp replay protection, retries with backoff, idempotent consumers, ordering, event versioning and secret rotation. Use when the user builds a webhook provider, writes a webhook receiver/endpoint, debugs "signature verification failed", or asks how to deliver events to customers. Includes a sign/verify CLI and tested verification snippets for Python, Node.js and PHP.
license: MIT
compatibility: Python 3.9+ for the CLI. Node.js 18+ and PHP 8.0+ for the snippets.
metadata:
  author: Saizul Amin
  version: "0.1.0"
---

# Webhook design

Paths such as `scripts/...` and `references/...` are relative to this skill's folder (`${CLAUDE_SKILL_DIR}` in Claude Code). Run scripts from the user's project with that folder's path.

## When to use

- Designing outgoing webhooks for your platform (provider side).
- Writing an endpoint that receives webhooks (consumer side).
- Debugging signature failures, duplicate deliveries or out-of-order events.

## When not to use

- Internal service-to-service events with a broker (Kafka, SQS, NATS): use the broker's
  delivery guarantees instead of HTTP callbacks.
- Real-time streams to browsers: use SSE or WebSockets.

## Workflow

### Provider side

1. **Envelope and naming** from [references/design.md](references/design.md):
   `{"id", "type": "invoice.paid", "created_at", "api_version", "data": {...}}`. Event
   types are `resource.past_tense_verb`. Pick thin events (IDs, client fetches) or fat
   events (full object snapshot) and say which.
2. **Sign every delivery.** Default to the Standard Webhooks scheme: headers
   `webhook-id`, `webhook-timestamp`, `webhook-signature: v1,<base64 HMAC-SHA256 of
   "{id}.{timestamp}.{body}">`. Per-endpoint secrets, shown once, rotatable with two
   active secrets during rotation (send both signatures, space-separated).
3. **Retries**: treat any 2xx as success; retry on timeouts, 429 and 5xx with exponential
   backoff and jitter for about 3 days (schedule in the reference); do not follow
   redirects; time out after 10-15 s; disable an endpoint after sustained failure and
   notify the owner.
4. **Delivery guarantees**: at-least-once, no global ordering. Document it. Keep the same
   `webhook-id` across retries so consumers can deduplicate.
5. **Security of the sender** (SSRF): resolve the target host and refuse private,
   loopback, link-local and metadata addresses at send time, not only at registration.
6. **Versioning**: stamp `api_version` on each event; endpoints pin a version; new fields
   are additive; breaking changes ship as a new version with a migration window.
7. **Tooling for customers**: a test-send button, delivery log with response codes,
   manual redelivery, and the verification snippets below.

### Consumer side

1. Read the **raw body** before any JSON parsing (signatures cover bytes, not objects).
2. Verify the signature with a constant-time compare and reject timestamps older than
   5 minutes. Use the snippets in [assets/snippets/](assets/snippets/)
   (`verify-webhook.mjs`, `verify-webhook.php`) or `scripts/webhook_signature.py` logic.
3. Deduplicate on the event/message ID (unique constraint), then **enqueue** and return
   2xx quickly; do the work asynchronously.
4. Do not trust payload contents for authorisation-sensitive actions in thin-event
   designs: fetch the current object from the provider's API.
5. Handle out-of-order delivery: compare the object's `updated_at`/version before
   overwriting newer state.

## Debugging signatures with the CLI

```bash
export WEBHOOK_SECRET=...            # never pass secrets as arguments
python scripts/webhook_signature.py sign --scheme standard --id msg_1 --body-file event.json
python scripts/webhook_signature.py verify --scheme github \
  --signature "sha256=..." --body-file captured-body.bin
python scripts/webhook_signature.py verify --scheme stripe \
  --signature "t=1700000000,v1=..." --body-file body.json --tolerance -1 --format json
```

Exit codes: 0 valid, 1 invalid, 2 usage. Common causes of failure are listed in
[references/design.md](references/design.md#why-verification-fails).

## Output

- Provider: event catalog table (`type | trigger | payload | version`), envelope schema,
  signing spec, retry schedule, and docs text for consumers.
- Consumer: handler code with verification, dedup table, queue hand-off and tests that
  use known-good test vectors.

## Example prompts

- "Design webhooks for our payments platform."
- "Write an Express endpoint that verifies Stripe webhooks."
- "Our GitHub webhook signature check always fails, here is the code."
