"""Reference implementation of Idempotency-Key handling (framework-agnostic, stdlib only).

Copy this file into a project and adapt the storage. It follows the IETF
httpapi "The Idempotency-Key HTTP Header Field" draft:

* first request with a key       -> run the handler, store the response
* retry with same key + payload  -> replay the stored response (no side effects)
* same key, different payload    -> 422 Unprocessable Content
* same key while first in flight -> 409 Conflict
* missing key where required     -> 400 Bad Request

Keys are scoped per client (for example the authenticated account id) so one
client can never replay another client's response. SQLite is used so the
example runs anywhere; the same schema works on PostgreSQL (see
references/storage.md).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from dataclasses import dataclass, field
from typing import Callable

DEFAULT_TTL_SECONDS = 24 * 60 * 60
DEFAULT_LOCK_SECONDS = 60
MAX_KEY_LENGTH = 255

SCHEMA = """
CREATE TABLE IF NOT EXISTS idempotency_keys (
    scope         TEXT    NOT NULL,
    key           TEXT    NOT NULL,
    fingerprint   TEXT    NOT NULL,
    state         TEXT    NOT NULL CHECK (state IN ('in_progress', 'completed')),
    status        INTEGER,
    headers       TEXT,
    body          BLOB,
    locked_until  REAL    NOT NULL,
    expires_at    REAL    NOT NULL,
    PRIMARY KEY (scope, key)
);
"""


@dataclass
class Response:
    status: int
    body: bytes = b""
    headers: dict = field(default_factory=dict)


def problem(status: int, title: str, detail: str) -> Response:
    body = json.dumps({"type": "about:blank", "title": title, "status": status, "detail": detail}).encode()
    return Response(status, body, {"Content-Type": "application/problem+json"})


def fingerprint(method: str, path: str, body: bytes) -> str:
    """Hash what makes two requests 'the same'. Canonicalise JSON so key order does not matter."""
    try:
        canonical = json.dumps(json.loads(body or b"null"), sort_keys=True, separators=(",", ":")).encode()
    except (ValueError, UnicodeDecodeError):
        canonical = body
    return hashlib.sha256(method.upper().encode() + b" " + path.encode() + b"\n" + canonical).hexdigest()


def parse_key(header_value: str | None) -> str | None:
    """Accept the draft's structured-field string form ("abc") and a bare token (abc)."""
    if header_value is None:
        return None
    value = header_value.strip()
    if len(value) >= 2 and value[0] == value[-1] == '"':
        value = value[1:-1]
    if not value or len(value) > MAX_KEY_LENGTH or not value.isprintable():
        raise ValueError("invalid Idempotency-Key")
    return value


class IdempotencyStore:
    def __init__(
        self,
        conn: sqlite3.Connection,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        lock_seconds: int = DEFAULT_LOCK_SECONDS,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.conn = conn
        self.ttl = ttl_seconds
        self.lock = lock_seconds
        self.clock = clock
        conn.executescript(SCHEMA)

    def begin(self, scope: str, key: str, fp: str):
        """Claim a key. Returns ('new', None), ('replay', Response) or ('conflict'|'mismatch', Response)."""
        now = self.clock()
        with self.conn:  # one transaction: the INSERT is the lock
            self.conn.execute(
                "DELETE FROM idempotency_keys WHERE scope = ? AND key = ? AND expires_at < ?", (scope, key, now)
            )
            cur = self.conn.execute(
                "INSERT OR IGNORE INTO idempotency_keys (scope, key, fingerprint, state, locked_until, expires_at)"
                " VALUES (?, ?, ?, 'in_progress', ?, ?)",
                (scope, key, fp, now + self.lock, now + self.ttl),
            )
            if cur.rowcount == 1:
                return "new", None
            row = self.conn.execute(
                "SELECT fingerprint, state, status, headers, body, locked_until FROM idempotency_keys"
                " WHERE scope = ? AND key = ?",
                (scope, key),
            ).fetchone()
        stored_fp, state, status, headers, body, locked_until = row
        if stored_fp != fp:
            return "mismatch", problem(
                422, "Idempotency key reused", "This Idempotency-Key was already used with a different request payload."
            )
        if state == "completed":
            replay = Response(status, body or b"", json.loads(headers or "{}"))
            replay.headers["Idempotent-Replayed"] = "true"
            return "replay", replay
        if locked_until < now:
            # The first attempt crashed before finishing: let this retry take over.
            with self.conn:
                self.conn.execute(
                    "UPDATE idempotency_keys SET locked_until = ? WHERE scope = ? AND key = ?",
                    (now + self.lock, scope, key),
                )
            return "new", None
        return "conflict", problem(
            409, "Request in progress", "A request with this Idempotency-Key is still being processed. Retry later."
        )

    def complete(self, scope: str, key: str, response: Response) -> None:
        with self.conn:
            self.conn.execute(
                "UPDATE idempotency_keys SET state = 'completed', status = ?, headers = ?, body = ?"
                " WHERE scope = ? AND key = ?",
                (response.status, json.dumps(response.headers), response.body, scope, key),
            )

    def release(self, scope: str, key: str) -> None:
        """Forget a key so the client may retry (use when the handler failed before any side effect)."""
        with self.conn:
            self.conn.execute("DELETE FROM idempotency_keys WHERE scope = ? AND key = ?", (scope, key))


def handle(
    store: IdempotencyStore,
    scope: str,
    method: str,
    path: str,
    headers: dict,
    body: bytes,
    handler: Callable[[], Response],
    required: bool = True,
) -> Response:
    """Wrap a non-idempotent handler (usually POST or PATCH)."""
    raw = next((v for k, v in headers.items() if k.lower() == "idempotency-key"), None)
    try:
        key = parse_key(raw)
    except ValueError:
        return problem(400, "Invalid Idempotency-Key", f"Send a unique string of 1-{MAX_KEY_LENGTH} characters.")
    if key is None:
        if required:
            return problem(400, "Idempotency-Key required", "This endpoint requires an Idempotency-Key header.")
        return handler()

    state, stored = store.begin(scope, key, fingerprint(method, path, body))
    if state != "new":
        return stored
    try:
        response = handler()
    except Exception:
        store.release(scope, key)
        raise
    if response.status >= 500:
        # Server errors are not cached so the client can retry with the same key.
        store.release(scope, key)
    else:
        store.complete(scope, key, response)
    return response
