import json
import shutil
import subprocess

import pytest

from conftest import FIXTURES, load_module, run_script

SCRIPT = "api-docs-writer/scripts/openapi_to_markdown.py"
docs = load_module(SCRIPT)


@pytest.fixture(scope="module")
def spec():
    return docs.load_spec(str(FIXTURES / "good.yaml"))


def test_render_structure(spec):
    md = docs.render(spec)
    assert md.startswith("# Orders API reference")
    assert "## Authentication" in md
    assert "[`GET /orders`](#list-orders)" in md
    assert "### Create an order" in md
    assert "> **Deprecated.**" in md
    assert "Authentication: none" in md  # /health has security: []
    assert "| `limit` | query | integer | no | Page size. |" in md


def test_curl_uses_env_vars_and_examples(spec):
    md = docs.render(spec)
    assert 'curl "https://api.example.com/v1/orders"' in md
    assert '-H "Authorization: Bearer $API_TOKEN"' in md
    header_example = spec["paths"]["/orders"]["post"]["parameters"][0]["schema"]["example"]
    assert '-H "Idempotency-Key: ' + header_example + '"' in md
    assert '"customer_id": "cus_123"' in md
    assert "/orders/3fa85f64-5717-4562-b3fc-2c963f66afa6" in md  # uuid path example


def test_curl_auth_variants():
    base = {"openapi": "3.1.0", "info": {"title": "t", "version": "1"}}
    op = {"responses": {"200": {"description": "ok"}}}
    cases = {
        "basic": ({"type": "http", "scheme": "basic"}, '-u "$API_USER:$API_PASSWORD"'),
        "hdr": ({"type": "apiKey", "in": "header", "name": "X-API-Key"}, '-H "X-API-Key: $API_KEY"'),
        "qry": ({"type": "apiKey", "in": "query", "name": "key"}, "?key=$API_KEY"),
        "oauth": ({"type": "oauth2", "flows": {}}, "Bearer $ACCESS_TOKEN"),
    }
    for name, (scheme, expected) in cases.items():
        spec = {**base, "components": {"securitySchemes": {name: scheme}}, "security": [{name: []}]}
        assert expected in docs.build_curl(spec, "https://x.test", "/a", "get", op, []), name


def test_shell_quote_escapes_single_quotes():
    assert docs.shell_quote("it's") == "'it'\\''s'"


def test_example_synthesis():
    spec = {
        "components": {
            "schemas": {
                "Node": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "format": "uuid"},
                        "child": {"$ref": "#/components/schemas/Node"},
                        "count": {"type": "integer", "minimum": 5},
                        "kind": {"type": "string", "enum": ["a", "b"]},
                        "tags": {"type": "array", "items": {"type": "string"}},
                        "maybe": {"type": ["string", "null"]},
                        "either": {"oneOf": [{"type": "boolean"}, {"type": "string"}]},
                    },
                }
            }
        }
    }
    value = docs.example_for(spec, {"$ref": "#/components/schemas/Node"})
    assert value["id"] == docs.FORMAT_EXAMPLES["uuid"]
    assert value["count"] == 5 and value["kind"] == "a" and value["tags"] == ["string"]
    assert value["maybe"] == "string" and value["either"] is True
    assert value["child"] is None  # a self-reference is not expanded


def test_allof_merges():
    spec = {}
    schema = {
        "allOf": [
            {"type": "object", "properties": {"a": {"type": "integer"}}},
            {"type": "object", "properties": {"b": {"type": "boolean"}}},
        ]
    }
    assert docs.example_for(spec, schema) == {"a": 1, "b": True}


def test_tag_filter(spec):
    md = docs.render(spec, tags=["Operations"])
    assert "### Health check" in md and "### List orders" not in md


def test_cli_json_and_output(tmp_path):
    out = run_script(SCRIPT, str(FIXTURES / "good.json"), "--format", "json", "--base-url", "https://sandbox.test")
    assert out.returncode == 0
    ops = json.loads(out.stdout)["operations"]
    assert len(ops) == 5
    assert all(o["curl"].startswith(('curl "https://sandbox.test', "curl -X")) for o in ops)
    target = tmp_path / "ref.md"
    assert run_script(SCRIPT, str(FIXTURES / "good.yaml"), "-o", str(target), "--no-curl").returncode == 0
    assert "curl" not in target.read_text()
    assert run_script(SCRIPT, str(tmp_path / "missing.yaml")).returncode == 2
    assert run_script(SCRIPT, "--help").returncode == 0


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash not available")
def test_generated_curl_is_valid_shell(spec):
    for path, method, op, params in docs.iter_operations(spec):
        command = docs.build_curl(spec, "https://api.example.com", path, method, op, params)
        result = subprocess.run(["bash", "-n", "-c", command], capture_output=True)
        assert result.returncode == 0, command
