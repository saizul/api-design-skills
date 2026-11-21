---
name: idempotency-keys
description: Make non-idempotent API operations (POST payments, orders, transfers, sends) safe to retry with an Idempotency-Key header - key scope, request fingerprinting, storing and replaying responses, concurrent duplicates (409), payload mismatch (422), expiry, and database schema for PostgreSQL/MySQL/Redis. Use when the user asks how to prevent duplicate charges/orders on retries, mentions idempotency keys, at-least-once delivery, double submits, or designs a payments or order-creation endpoint. Includes a tested reference implementation.
license: MIT
compatibility: Reference implementation needs Python 3.9+ (stdlib sqlite3). Patterns apply to any stack.
metadata:
  author: Saizul Amin
  version: "0.1.0"
---

# Idempotency keys

Clients retry after timeouts and network errors. Without idempotency a retry can
charge a card twice. The client sends a unique `Idempotency-Key`; the server runs the
operation once and replays the stored result for every retry.

Paths such as `assets/...` and `references/...` are relative to this skill's folder (`${CLAUDE_SKILL_DIR}` in Claude Code). Copy or import the reference code from there.

## When to use

- POST endpoints with side effects: payments, refunds, orders, transfers, emails/SMS,
  provisioning, anything that calls a third party.
- PATCH endpoints that are not naturally idempotent (increments, appends).
- Webhook consumers (use the event ID as the key).

## When not to use

- GET, HEAD, PUT and DELETE are idempotent by definition (still use ETags for lost-update
  protection).
- When a natural unique key exists and is enough (for example a client-generated order
  UUID with a unique constraint and "create or return existing" semantics).

## Workflow

1. **Contract** (document it, based on the IETF httpapi Idempotency-Key draft):
   - Header `Idempotency-Key: "<uuid v4>"` (a quoted string per the draft; also accept
     the bare value). 1-255 printable characters.
   - Required on the listed endpoints (400 if missing), optional elsewhere.
   - Same key + same payload: original status and body replayed (add
     `Idempotent-Replayed: true`, a common non-standard header).
   - Same key + different payload: 422. Same key while the first is in flight: 409 with
     `Retry-After`.
   - Keys expire after 24 hours (state the window).
2. **Scope keys** per authenticated client/account (and per endpoint if you like):
   primary key `(scope, key)`. Never let one tenant replay another tenant's response.
3. **Fingerprint** the request: method + path + canonical body hash. Exclude volatile
   headers.
4. **Store atomically.** Insert the key in `in_progress` state in the same transaction
   boundary that makes the claim exclusive (unique constraint). Then run the operation,
   then store status + headers + body and mark `completed`. Schemas for PostgreSQL,
   MySQL and Redis are in [references/storage.md](references/storage.md).
5. **Failure rules:**
   - 2xx and 4xx responses are stored and replayed (a validation error is a final answer).
   - 5xx or a crash before completion: release the key so the client can retry, **unless**
     a side effect already happened. For multi-step work use recovery points
     (see the reference) so a retry resumes instead of repeating.
   - A lock older than the lock timeout is considered abandoned and may be taken over.
6. **Wire it in** using [assets/idempotency_store.py](assets/idempotency_store.py)
   (`handle()` wraps any handler) or translate it to the user's framework as middleware.
7. **Test**: retry replays the same body without a second side effect; different payload
   gives 422; concurrent duplicate gives 409; another tenant using the same key gets a fresh
   result; expired keys are processed again.

## Output

1. The contract text for the API docs.
2. Storage schema/migration for the user's database.
3. Middleware or handler code and the tests above.
4. Client guidance: generate a UUID per logical operation, reuse it on retries only,
   retry with exponential backoff on network errors, 409 and 5xx.

## Example prompts

- "Users sometimes get charged twice when the app retries. Fix our /payments endpoint."
- "Add Idempotency-Key support to this Express API with Postgres."
- "What should happen if the same idempotency key arrives with a different body?"
