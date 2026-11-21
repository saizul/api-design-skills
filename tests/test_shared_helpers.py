"""Each skill ships its own copy of the OpenAPI helpers so it can be installed alone.
This test keeps the copies identical."""

import inspect

import pytest

from conftest import load_module

SCRIPTS = [
    "openapi-review/scripts/openapi_lint.py",
    "api-security-review/scripts/api_security_scan.py",
    "api-docs-writer/scripts/openapi_to_markdown.py",
    "pagination-filtering/scripts/pagination_audit.py",
    "api-changelog-deprecation/scripts/deprecation_headers.py",
    "error-responses/scripts/problem_lint.py",
]
MODULES = [load_module(s) for s in SCRIPTS]


@pytest.mark.parametrize("name", ["load_spec", "resolve"])
def test_helpers_identical(name):
    sources = {inspect.getsource(getattr(m, name)) for m in MODULES}
    assert len(sources) == 1


def test_iter_operations_identical():
    sources = {inspect.getsource(m.iter_operations) for m in MODULES if hasattr(m, "iter_operations")}
    assert len(sources) == 1


def test_yaml_missing_message(monkeypatch, tmp_path):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "yaml":
            raise ImportError("no yaml")
        return real_import(name, *args, **kwargs)

    spec = tmp_path / "spec.yaml"
    spec.write_text("openapi: 3.1.0\n")
    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(MODULES[0].SpecError, match="PyYAML"):
        MODULES[0].load_spec(str(spec))
