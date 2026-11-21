import json
import sqlite3

import pytest

from conftest import load_module

idem = load_module("idempotency-keys/assets/idempotency_store.py")


class Clock:
    def __init__(self):
        self.now = 1_000_000.0

    def __call__(self):
        return self.now


@pytest.fixture
def env():
    clock = Clock()
    store = idem.IdempotencyStore(sqlite3.connect(":memory:"), ttl_seconds=3600, lock_seconds=30, clock=clock)
    calls = []

    def handler():
        calls.append(1)
        return idem.Response(
            201, json.dumps({"id": f"pay_{len(calls)}"}).encode(), {"Content-Type": "application/json"}
        )

    return store, clock, calls, handler


def call(store, handler, key='"key-1"', body=b'{"amount": 500, "currency": "usd"}', scope="acct_1"):
    headers = {"Idempotency-Key": key} if key is not None else {}
    return idem.handle(store, scope, "POST", "/v1/payments", headers, body, handler)


def test_first_call_runs_and_retry_replays(env):
    store, _, calls, handler = env
    first = call(store, handler)
    second = call(store, handler)
    assert first.status == second.status == 201
    assert first.body == second.body
    assert second.headers["Idempotent-Replayed"] == "true"
    assert len(calls) == 1


def test_json_key_order_does_not_matter(env):
    store, _, calls, handler = env
    call(store, handler, body=b'{"amount": 500, "currency": "usd"}')
    replay = call(store, handler, body=b'{"currency":"usd","amount":500}')
    assert replay.status == 201 and len(calls) == 1


def test_different_payload_is_422(env):
    store, _, calls, handler = env
    call(store, handler)
    resp = call(store, handler, body=b'{"amount": 900}')
    assert resp.status == 422
    assert resp.headers["Content-Type"] == "application/problem+json"
    assert len(calls) == 1


def test_concurrent_duplicate_is_409(env):
    store, _, _, _ = env
    fp = idem.fingerprint("POST", "/v1/payments", b"{}")
    assert store.begin("acct_1", "k", fp) == ("new", None)
    state, resp = store.begin("acct_1", "k", fp)
    assert state == "conflict" and resp.status == 409


def test_stale_lock_can_be_taken_over(env):
    store, clock, _, _ = env
    fp = idem.fingerprint("POST", "/x", b"{}")
    store.begin("acct_1", "k", fp)
    clock.now += 31
    assert store.begin("acct_1", "k", fp)[0] == "new"


def test_scopes_are_isolated(env):
    store, _, calls, handler = env
    call(store, handler, scope="acct_1")
    other = call(store, handler, scope="acct_2")
    assert other.status == 201 and len(calls) == 2
    assert "Idempotent-Replayed" not in other.headers


def test_expired_keys_run_again(env):
    store, clock, calls, handler = env
    call(store, handler)
    clock.now += 3601
    call(store, handler)
    assert len(calls) == 2


def test_server_errors_are_not_cached(env):
    store, _, _, _ = env
    attempts = []

    def flaky():
        attempts.append(1)
        return idem.Response(503 if len(attempts) == 1 else 201, b"{}")

    assert call(store, flaky).status == 503
    assert call(store, flaky).status == 201
    assert call(store, flaky).status == 201
    assert len(attempts) == 2


def test_client_errors_are_cached(env):
    store, _, _, _ = env
    attempts = []

    def invalid():
        attempts.append(1)
        return idem.Response(422, b'{"title": "invalid"}')

    assert call(store, invalid).status == 422
    assert call(store, invalid).status == 422
    assert len(attempts) == 1


def test_exception_releases_key(env):
    store, _, calls, handler = env

    def boom():
        raise RuntimeError("down")

    with pytest.raises(RuntimeError):
        call(store, boom)
    assert call(store, handler).status == 201


def test_missing_and_invalid_keys(env):
    store, _, calls, handler = env
    assert call(store, handler, key=None).status == 400
    assert call(store, handler, key='""').status == 400
    assert call(store, handler, key="x" * 300).status == 400
    optional = idem.handle(store, "acct_1", "POST", "/x", {}, b"{}", handler, required=False)
    assert optional.status == 201


def test_parse_key_forms():
    assert idem.parse_key('"abc"') == "abc"
    assert idem.parse_key("abc") == "abc"
    assert idem.parse_key(None) is None
    with pytest.raises(ValueError):
        idem.parse_key("bad\nkey")
