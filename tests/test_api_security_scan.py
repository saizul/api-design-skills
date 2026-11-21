import json

from conftest import FIXTURES, load_module, run_script

SCRIPT = "api-security-review/scripts/api_security_scan.py"
scan_mod = load_module(SCRIPT)


def scan(name):
    return scan_mod.scan(scan_mod.load_spec(str(FIXTURES / name)))


def by_rule(findings):
    out = {}
    for f in findings:
        out.setdefault(f["rule"], []).append(f)
    return out


def test_good_spec_has_no_errors_or_warnings():
    findings = scan("good.yaml")
    assert [f for f in findings if f["severity"] != "info"] == []
    assert {f["rule"] for f in findings} == {"object-access-review", "unauthenticated-operation"}


def test_insecure_spec_findings():
    rules = by_rule(scan("insecure.yaml"))
    for rule in ("api-key-in-query", "oauth-implicit", "plain-http-server", "sensitive-response-field"):
        assert rules[rule][0]["severity"] == "error", rule
    assert {
        "basic-auth",
        "open-request-schema",
        "unbounded-page-size",
        "privileged-path",
        "write-without-scope",
        "url-input",
        "mixed-environments",
        "sequential-id",
    } <= set(rules)


def test_nested_sensitive_field_found():
    locations = [f["location"] for f in scan("insecure.yaml") if f["rule"] == "sensitive-response-field"]
    assert any(loc.endswith("profile.access_token") for loc in locations)
    assert any(loc.endswith(" password") for loc in locations)


def test_owasp_labels():
    for f in scan("insecure.yaml"):
        assert f["owasp"] in scan_mod.OWASP
        assert f["category"] == scan_mod.OWASP[f["owasp"]]


def test_no_schemes_is_error():
    rules = by_rule(scan("bad.yaml"))
    assert rules["no-security-schemes"][0]["severity"] == "error"
    assert rules["privileged-path"][0]["severity"] == "error"  # public admin path


def test_write_only_secret_not_flagged():
    spec = {
        "openapi": "3.1.0",
        "info": {"title": "t", "version": "1"},
        "components": {"securitySchemes": {"b": {"type": "http", "scheme": "bearer"}}},
        "security": [{"b": []}],
        "paths": {
            "/me": {
                "get": {
                    "responses": {
                        "200": {
                            "description": "ok",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {"password": {"type": "string", "writeOnly": True}},
                                    }
                                }
                            },
                        }
                    }
                }
            }
        },
    }
    assert "sensitive-response-field" not in by_rule(scan_mod.scan(spec))


def test_localhost_http_allowed():
    spec = {"openapi": "3.1.0", "info": {"title": "t", "version": "1"}, "servers": [{"url": "http://localhost:8000"}]}
    assert "plain-http-server" not in by_rule(scan_mod.scan(spec))


def test_cli():
    out = run_script(SCRIPT, str(FIXTURES / "insecure.yaml"), "--format", "json", "--min-severity", "error")
    assert out.returncode == 1
    data = json.loads(out.stdout)
    assert all(f["severity"] == "error" for f in data["findings"])
    assert run_script(SCRIPT, str(FIXTURES / "good.yaml")).returncode == 0
    text = run_script(SCRIPT, str(FIXTURES / "insecure.yaml"), "--fail-on", "never")
    assert text.returncode == 0
    assert b"API2 Broken Authentication" in text.stdout
    assert run_script(SCRIPT, "--help").returncode == 0
