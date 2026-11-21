import json

import pytest

from conftest import FIXTURES, load_module, run_script

SCRIPT = "pagination-filtering/scripts/pagination_audit.py"
audit_mod = load_module(SCRIPT)
cursor = load_module("pagination-filtering/assets/cursor_pagination.py")
SECRET = b"test-cursor-secret"


def rules(findings):
    return {f["rule"] for f in findings}


def test_good_spec_clean():
    assert audit_mod.audit(audit_mod.load_spec(str(FIXTURES / "good.yaml"))) == []


def test_bad_spec_findings():
    found = rules(audit_mod.audit(audit_mod.load_spec(str(FIXTURES / "bad.yaml"))))
    assert {
        "no-pagination",
        "top-level-array",
        "page-size-maximum",
        "page-size-default",
        "no-next-link",
        "offset-pagination",
        "sort-allowlist",
        "mixed-pagination-styles",
        "mixed-page-size-names",
    } <= found


def test_single_resource_with_array_field_ignored():
    spec = {
        "paths": {
            "/orders/{id}": {
                "get": {
                    "responses": {
                        "200": {
                            "description": "x",
                            "content": {
                                "application/json": {
                                    "schema": {"type": "object", "properties": {"items": {"type": "array"}}}
                                }
                            },
                        }
                    }
                }
            }
        }
    }
    assert rules(audit_mod.audit(spec)) == {"no-collections"}


def test_link_header_satisfies_bare_array():
    spec = {
        "paths": {
            "/things": {
                "get": {
                    "parameters": [
                        {"name": "cursor", "in": "query"},
                        {"name": "limit", "in": "query", "schema": {"type": "integer", "maximum": 50, "default": 10}},
                    ],
                    "responses": {
                        "200": {
                            "description": "x",
                            "headers": {"Link": {"schema": {"type": "string"}}},
                            "content": {"application/json": {"schema": {"type": "array", "items": {}}}},
                        }
                    },
                }
            }
        }
    }
    assert rules(audit_mod.audit(spec)) == {"top-level-array"}


def test_cli():
    assert run_script(SCRIPT, str(FIXTURES / "good.yaml")).returncode == 0
    out = run_script(SCRIPT, str(FIXTURES / "bad.yaml"), "--format", "json")
    assert out.returncode == 1 and json.loads(out.stdout)["count"] > 0
    assert run_script(SCRIPT, str(FIXTURES / "bad.yaml"), "--fail-on", "never").returncode == 0
    assert run_script(SCRIPT, "--help").returncode == 0


def test_cursor_roundtrip():
    token = cursor.encode_cursor({"created_at": "2026-01-15T09:30:00Z", "id": 42}, SECRET, sort="-created_at")
    assert "=" not in token
    assert cursor.decode_cursor(token, SECRET, sort="-created_at") == {"created_at": "2026-01-15T09:30:00Z", "id": 42}


def test_cursor_tamper_and_sort_mismatch():
    token = cursor.encode_cursor({"id": 1}, SECRET)
    body, mac = token.split(".")
    forged = cursor._b64(b'{"p":{"id":999},"s":"","v":1}') + "." + mac
    for bad in (forged, token[:-2] + "xx", "garbage", ""):
        with pytest.raises(cursor.InvalidCursor):
            cursor.decode_cursor(bad, SECRET)
    with pytest.raises(cursor.InvalidCursor, match="sort"):
        cursor.decode_cursor(token, SECRET, sort="name")
    with pytest.raises(cursor.InvalidCursor):
        cursor.decode_cursor(token, b"other-secret")


def test_clamp_limit():
    assert cursor.clamp_limit(None) == 20
    assert cursor.clamp_limit("50") == 50
    assert cursor.clamp_limit(1000) == 100
    for bad in ("0", "-1", "abc"):
        with pytest.raises(ValueError):
            cursor.clamp_limit(bad)


def test_paginate_keyset_walk():
    rows = [{"id": i, "created_at": f"2026-01-{i:02d}"} for i in range(1, 8)]
    ordered = sorted(rows, key=lambda r: (r["created_at"], r["id"]), reverse=True)

    def fetch(after, limit):
        data = ordered
        if after:
            data = [r for r in ordered if (r["created_at"], r["id"]) < (after["created_at"], after["id"])]
        return data[: limit + 1]

    seen, after = [], None
    while True:
        page = cursor.paginate(fetch(after, 3), 3, ("created_at", "id"), SECRET)
        seen += [r["id"] for r in page["data"]]
        if not page["has_more"]:
            assert page["next_cursor"] is None
            break
        after = cursor.decode_cursor(page["next_cursor"], SECRET)
    assert seen == [7, 6, 5, 4, 3, 2, 1]


def test_link_header_roundtrip():
    header = cursor.link_header("https://api.test/v1/orders?status=paid&cursor=old&limit=10", "NEXT", "PREV")
    links = cursor.parse_link_header(header)
    assert links["next"] == "https://api.test/v1/orders?status=paid&limit=10&cursor=NEXT"
    assert links["prev"].endswith("cursor=PREV")
    assert cursor.link_header("https://api.test/x", None) is None
