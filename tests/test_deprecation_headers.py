import json
from datetime import datetime, timezone

import pytest

from conftest import FIXTURES, load_module, run_script

SCRIPT = "api-changelog-deprecation/scripts/deprecation_headers.py"
dep = load_module(SCRIPT)


def test_rfc_examples():
    # RFC 9745 section 2.1 example: @1688169599 is 2023-06-30T23:59:59Z
    when = dep.parse_when("@1688169599")
    assert when == datetime(2023, 6, 30, 23, 59, 59, tzinfo=timezone.utc)
    assert dep.deprecation_value(when) == "@1688169599"
    # RFC 8594 style HTTP-date
    assert dep.sunset_value(dep.parse_when("2018-11-11T23:59:59Z")) == "Sun, 11 Nov 2018 23:59:59 GMT"
    assert dep.parse_when("Sun, 11 Nov 2018 23:59:59 GMT") == datetime(2018, 11, 11, 23, 59, 59, tzinfo=timezone.utc)


def test_build_headers():
    headers, warnings = dep.build_headers(
        dep.parse_when("2026-03-01"),
        dep.parse_when("2026-09-01"),
        "https://docs.test/migrate",
        "https://docs.test/policy",
    )
    assert headers["Deprecation"] == "@1772323200"
    assert headers["Sunset"] == "Tue, 01 Sep 2026 00:00:00 GMT"
    assert headers["Link"] == (
        '<https://docs.test/migrate>; rel="deprecation"; type="text/html", '
        '<https://docs.test/policy>; rel="sunset"; type="text/html"'
    )
    assert warnings == []


def test_build_headers_warnings_and_errors():
    _, warnings = dep.build_headers(dep.parse_when("2026-03-01"), dep.parse_when("2026-03-31"))
    assert any("30 days" in w for w in warnings)
    assert any("Link" in w for w in warnings)
    _, warnings = dep.build_headers(dep.parse_when("2026-03-01"), None, "https://x.test")
    assert any("no sunset" in w for w in warnings)
    with pytest.raises(ValueError):
        dep.build_headers(dep.parse_when("2026-03-01"), dep.parse_when("2026-02-01"))
    with pytest.raises(ValueError):
        dep.parse_when("next tuesday")


def test_check_spec():
    good = dep.load_spec(str(FIXTURES / "good.yaml"))
    assert dep.check_spec(good, today=dep.parse_when("2026-01-01")) == []
    late = dep.check_spec(good, today=dep.parse_when("2031-01-01"))
    assert [f["rule"] for f in late] == ["past-sunset"]
    bad = {f["rule"] for f in dep.check_spec(dep.load_spec(str(FIXTURES / "bad.yaml")))}
    assert bad == {"no-replacement", "no-sunset-date", "no-deprecation-header", "no-sunset-header"}


def test_deprecated_params_and_fields():
    spec = {
        "paths": {
            "/a": {
                "get": {
                    "parameters": [{"name": "q", "in": "query", "deprecated": True}],
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
        "components": {
            "schemas": {
                "A": {
                    "properties": {
                        "old": {"type": "string", "deprecated": True},
                        "older": {"type": "string", "deprecated": True, "description": "Use new_field instead."},
                    }
                }
            }
        },
    }
    found = [(f["rule"], f["location"]) for f in dep.check_spec(spec)]
    assert ("param-no-replacement", "GET /a parameter q") in found
    assert ("field-no-replacement", "components.schemas.A.old") in found
    assert all("older" not in loc for _, loc in found)


def test_cli():
    out = run_script(
        SCRIPT,
        "headers",
        "--deprecated",
        "2026-03-01",
        "--sunset",
        "2026-09-01",
        "--link",
        "https://docs.test/m",
        "--format",
        "json",
    )
    assert out.returncode == 0
    assert json.loads(out.stdout)["headers"]["Deprecation"] == "@1772323200"
    nginx = run_script(SCRIPT, "headers", "--deprecated", "2026-03-01", "--format", "nginx")
    assert b"add_header Deprecation '@1772323200' always;" in nginx.stdout
    assert run_script(SCRIPT, "headers", "--deprecated", "2026-03-01", "--sunset", "2025-01-01").returncode == 1
    parsed = run_script(SCRIPT, "parse", "--deprecation", "@1688169599", "--sunset", "Sun, 11 Nov 2018 23:59:59 GMT")
    assert json.loads(parsed.stdout)["deprecation"].startswith("2023-06-30T23:59:59")
    assert run_script(SCRIPT, "parse", "--deprecation", "2023-06-30").returncode == 1
    assert run_script(SCRIPT, "check", str(FIXTURES / "good.yaml"), "--today", "2026-01-01").returncode == 0
    assert run_script(SCRIPT, "check", str(FIXTURES / "bad.yaml")).returncode == 1
    assert run_script(SCRIPT, "--help").returncode == 0
