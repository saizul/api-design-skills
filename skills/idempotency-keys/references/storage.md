# Storage patterns

## PostgreSQL

```sql
CREATE TABLE idempotency_keys (
    scope         text        NOT NULL,          -- account or API client id
    key           text        NOT NULL CHECK (length(key) BETWEEN 1 AND 255),
    fingerprint   text        NOT NULL,          -- sha256(method, path, canonical body)
    state         text        NOT NULL CHECK (state IN ('in_progress', 'completed')),
    recovery_point text,                         -- optional: last completed step
    status        smallint,
    headers       jsonb,
    body          bytea,
    locked_until  timestamptz NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now(),
    expires_at    timestamptz NOT NULL,
    PRIMARY KEY (scope, key)
);
CREATE INDEX idempotency_keys_expires ON idempotency_keys (expires_at);
```

Claim a key:

```sql
INSERT INTO idempotency_keys (scope, key, fingerprint, state, locked_until, expires_at)
VALUES ($1, $2, $3, 'in_progress', now() + interval '60 seconds', now() + interval '24 hours')
ON CONFLICT (scope, key) DO NOTHING
RETURNING key;            -- a row back means "new"; no row means "look it up"
```

Look up an existing key with `SELECT ... FOR UPDATE` inside a transaction to decide
replay (completed), 422 (fingerprint differs), 409 (in progress, lock not expired) or
takeover (lock expired).

Purge daily: `DELETE FROM idempotency_keys WHERE expires_at < now();`

## MySQL 8

Same table with `VARCHAR(255)`, `JSON`, `LONGBLOB`, `DATETIME(6)`; claim with
`INSERT IGNORE` and check `ROW_COUNT() = 1`.

## Redis

```
SET idem:{scope}:{key} '{"fp":"...","state":"in_progress"}' NX EX 86400
```

`NX` gives the exclusive claim. On completion `SET ... XX KEEPTTL` with the stored
response. Redis is fine for short windows; keep the business write and the key in the
same database when you need them to commit atomically.

## Recovery points (multi-step operations)

For an operation such as "create order -> charge card -> send email":

1. Store `recovery_point = 'started'` with the key.
2. Each step runs in its own transaction and advances `recovery_point`
   (`order_created`, `charge_created`). External calls pass their own idempotency key
   derived from yours (`{key}:charge`) so the payment provider deduplicates too.
3. A retry reads `recovery_point` and continues from there instead of starting over.
4. When the last step finishes, store the response and mark `completed`.

This is the pattern described in Brandur Leach's "Implementing Stripe-like Idempotency
Keys in Postgres".

## Node.js / Express sketch

```js
app.post('/v1/payments', requireAuth, express.json(), async (req, res, next) => {
  const key = req.get('Idempotency-Key')?.replace(/^"|"$/g, '');
  if (!key) return res.status(400).type('application/problem+json')
    .json({ type: 'about:blank', title: 'Bad Request', status: 400, detail: 'Idempotency-Key header is required.' });
  const scope = req.user.accountId;
  const fp = fingerprint(req.method, req.path, req.body);  // sha256 of canonical JSON
  const claim = await store.begin(scope, key, fp);          // 'new' | 'replay' | 'conflict' | 'mismatch'
  if (claim.state !== 'new') {
    res.set(claim.response.headers);
    return res.status(claim.response.status).send(claim.response.body);
  }
  try {
    const payment = await payments.create(req.body, { idempotencyKey: `${key}:psp` });
    const body = JSON.stringify(payment);
    await store.complete(scope, key, { status: 201, headers: { 'Content-Type': 'application/json' }, body });
    res.status(201).type('application/json').send(body);
  } catch (err) {
    await store.release(scope, key);   // only if no side effect happened
    next(err);
  }
});
```
