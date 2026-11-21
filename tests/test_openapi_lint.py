import json

import pytest

from conftest import FIXTURES, load_module, run_script

SCRIPT = "openapi-review/scripts/openapi_lint.py"
lint_mod = load_module(SCRIPT)


def rules(findings, severity=None):
    return {f["rule"] for f in findings if severity is None or f["severity"] == severity}


def test_good_spec_is_clean():
    spec = lint_mod.load_spec(str(FIXTURES / "good.yaml"))
    assert lint_mod.lint(spec) == []


def test_json_and_yaml_give_same_result():
    yaml_spec = lint_mod.load_spec(str(FIXTURES / "good.yaml"))
    json_spec = lint_mod.load_spec(str(FIXTURES / "good.json"))
    assert yaml_spec == json_spec


def test_bad_spec_errors():
    findings = lint_mod.lint(lint_mod.load_spec(str(FIXTURES / "bad.yaml")))
    errors = rules(findings, "error")
    assert {
        "operation-id",
        "operation-id-unique",
        "path-parameter-declared",
        "response-description",
        "success-response",
        "info-version",
    } <= errors


def test_bad_spec_warnings():
    findings = lint_mod.lint(lint_mod.load_spec(str(FIXTURES / "bad.yaml")))
    warnings = rules(findings, "warning")
    assert {
        "path-casing",
        "path-verb",
        "path-trailing-slash",
        "get-request-body",
        "error-responses",
        "examples",
        "parameter-description",
        "operation-id-style",
        "property-casing",
        "security-schemes",
        "info-description",
    } <= warnings


def test_path_verb_detects_camel_case():
    spec = {
        "openapi": "3.1.0",
        "info": {"title": "t", "version": "1"},
        "paths": {"/createInvoice": {}, "/invoice-lines": {}},
    }
    flagged = [f["location"] for f in lint_mod.lint(spec) if f["rule"] == "path-verb"]
    assert flagged == ["/createInvoice"]


def test_swagger2_rejected():
    findings = lint_mod.lint({"swagger": "2.0", "info": {"title": "x", "version": "1"}})
    assert "spec-version" in rules(findings, "error")


def test_operation_security_missing():
    spec = {
        "openapi": "3.0.3",
        "info": {"title": "t", "version": "1", "description": "d"},
        "components": {"securitySchemes": {"k": {"type": "apiKey", "in": "header", "name": "X-Key"}}},
        "paths": {"/a": {"get": {"operationId": "a", "summary": "a", "responses": {"200": {"description": "ok"}}}}},
    }
    assert "operation-security" in rules(lint_mod.lint(spec))
    spec["paths"]["/a"]["get"]["security"] = []
    assert "operation-security" not in rules(lint_mod.lint(spec))


def test_resolve_handles_cycles_and_missing():
    spec = {"components": {"schemas": {"A": {"$ref": "#/components/schemas/A"}}}}
    assert lint_mod.resolve(spec, {"$ref": "#/components/schemas/A"}) == {}
    assert lint_mod.resolve(spec, {"$ref": "#/nope"}) == {}
    assert lint_mod.resolve(spec, {"$ref": "other.yaml#/x"}) == {}


@pytest.mark.parametrize(
    "name,style",
    [
        ("listOrders", "camel"),
        ("list_orders", "snake"),
        ("ListOrders", "pascal"),
        ("orders", None),
        ("list-orders", "kebab"),
    ],
)
def test_casing(name, style):
    assert lint_mod.casing(name) == style


def test_cli_exit_codes_and_json(tmp_path):
    good = run_script(SCRIPT, str(FIXTURES / "good.yaml"))
    assert good.returncode == 0
    assert b"No findings" in good.stdout

    bad = run_script(SCRIPT, str(FIXTURES / "bad.yaml"), "--format", "json")
    assert bad.returncode == 1
    payload = json.loads(bad.stdout)
    assert payload["count"] == len(payload["findings"]) > 0

    never = run_script(SCRIPT, str(FIXTURES / "bad.yaml"), "--fail-on", "never")
    assert never.returncode == 0

    broken = tmp_path / "broken.json"
    broken.write_text("{not json")
    assert run_script(SCRIPT, str(broken)).returncode == 2
    assert run_script(SCRIPT, str(tmp_path / "missing.yaml")).returncode == 2


def test_cli_ignore_and_list_rules():
    out = run_script(
        SCRIPT,
        str(FIXTURES / "insecure.yaml"),
        "--fail-on",
        "warning",
        "--ignore",
        "error-responses",
        "--ignore",
        "examples",
        "--ignore",
        "parameter-description",
        "--ignore",
        "info-description",
    )
    assert out.returncode == 0, out.stdout
    listed = run_script(SCRIPT, "--list-rules", "x")
    assert b"operation-id" in listed.stdout


def test_help():
    assert run_script(SCRIPT, "--help").returncode == 0
