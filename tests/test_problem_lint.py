import json

from conftest import FIXTURES, load_module, run_script

SCRIPT = "error-responses/scripts/problem_lint.py"
pl = load_module(SCRIPT)


def rules(findings):
    return {f["rule"] for f in findings}


def test_valid_problem_is_clean():
    doc = json.loads((FIXTURES / "problems" / "valid.json").read_text())
    assert pl.lint_problem(doc, http_status=422) == []


def test_leaky_problems():
    docs = json.loads((FIXTURES / "problems" / "leaky.json").read_text())
    assert {"status-integer", "detail-leak", "extension-name", "type-missing"} <= rules(pl.lint_problem(docs[0]))
    assert rules(pl.lint_problem(docs[1])) == {"blank-title"}
    assert rules(pl.lint_problem(docs[2])) == {"not-object"}


def test_status_checks():
    assert "status-mismatch" in rules(
        pl.lint_problem({"type": "about:blank", "title": "Not Found", "status": 404}, http_status=410)
    )
    assert "status-not-error" in rules(pl.lint_problem({"title": "OK", "status": 200}))
    assert "status-integer" in rules(pl.lint_problem({"title": "x", "status": True}))
    assert "status-missing" in rules(pl.lint_problem({"type": "https://e.test/p", "title": "x"}))


def test_type_checks():
    assert "type-uri" in rules(pl.lint_problem({"type": "not a uri", "title": "x", "status": 400}))
    assert "type-string" in rules(pl.lint_problem({"type": 5, "title": "x", "status": 400}))
    assert "type-https" in rules(pl.lint_problem({"type": "http://e.test/p", "title": "x", "status": 400}))


def test_leak_patterns():
    for detail in (
        "SQLSTATE[23000]: Integrity constraint violation",
        "java.lang.NullPointerException at com.acme.Foo.bar(Foo.java:42)",
        "TypeError: Cannot read properties of undefined",
    ):
        assert "detail-leak" in rules(pl.lint_problem({"title": "x", "status": 500, "detail": detail})), detail
    safe = {"title": "x", "status": 422, "detail": "Validation Error: quantity must be at least 1"}
    assert "detail-leak" not in rules(pl.lint_problem(safe))


def test_errors_items():
    doc = {"type": "https://e.test/v", "title": "Invalid", "status": 422, "errors": [{"message": "bad"}]}
    assert "errors-item" in rules(pl.lint_problem(doc))


def test_spec_mode():
    assert pl.lint_spec(pl.load_spec(str(FIXTURES / "good.yaml"))) == []
    found = rules(pl.lint_spec(pl.load_spec(str(FIXTURES / "bad.yaml"))))
    assert found == {"no-error-body", "not-problem-json"}


def test_spec_mode_lints_examples():
    spec = {
        "paths": {
            "/a": {
                "get": {
                    "responses": {
                        "404": {
                            "description": "x",
                            "content": {
                                "application/problem+json": {
                                    "example": {"type": "about:blank", "title": "Missing", "status": 400}
                                }
                            },
                        }
                    }
                }
            }
        }
    }
    assert {"blank-title", "status-mismatch"} <= rules(pl.lint_spec(spec))


def test_cli():
    ok = run_script(SCRIPT, "doc", str(FIXTURES / "problems" / "valid.json"), "--status", "422")
    assert ok.returncode == 0 and b"No findings" in ok.stdout
    bad = run_script(SCRIPT, "doc", "-", "--format", "json", stdin=b'{"status": "500"}')
    assert bad.returncode == 1
    assert json.loads(bad.stdout)["count"] >= 1
    spec = run_script(SCRIPT, "spec", str(FIXTURES / "bad.yaml"), "--fail-on", "warning")
    assert spec.returncode == 1
    assert run_script(SCRIPT, "doc", "-", stdin=b"{oops").returncode == 2
    assert run_script(SCRIPT, "--help").returncode == 0
