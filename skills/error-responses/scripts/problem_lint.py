#!/usr/bin/env python3
"""Check error payloads against RFC 9457 (Problem Details for HTTP APIs).

Modes
  problem_lint.py doc FILE [FILE ...]   lint captured error bodies (JSON object
                                        or array of objects; - for stdin)
  problem_lint.py spec OPENAPI          check that 4xx/5xx responses in an
                                        OpenAPI 3.x document use
                                        application/problem+json

Exit codes: 0 = no findings at or above --fail-on, 1 = findings, 2 = usage or
parse error.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from http import HTTPStatus
from pathlib import Path

SEVERITY_RANK = {"info": 0, "warning": 1, "error": 2}
STANDARD_MEMBERS = {"type", "title", "status", "detail", "instance"}
EXTENSION_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]{2,}$")
LEAK_PATTERNS = [
    (re.compile(r"Traceback \(most recent call last\)"), "Python traceback"),
    (re.compile(r"\bat [\w.$]+\([\w.]+:\d+\)"), "Java/JS stack frame"),
    (re.compile(r"\bSQLSTATE\[|\bORA-\d{5}\b|syntax error at or near", re.I), "SQL error"),
    (re.compile(r"(/home/|/var/www/|/usr/src/|C:\\\\Users\\\\)"), "server file path"),
    (re.compile(r"\b[A-Z]\w*(Exception|Error): "), "raw exception message"),
]
HTTP_METHODS = ("get", "put", "post", "delete", "options", "head", "patch", "trace")


class SpecError(Exception):
    """Raised when a document cannot be read."""


def load_spec(path: str) -> dict:
    """Load a JSON or YAML OpenAPI document."""
    try:
        text = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise SpecError(f"cannot read {path}: {exc}") from exc
    if path.endswith(".json") or text.lstrip().startswith("{"):
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise SpecError(f"invalid JSON: {exc}") from exc
    else:
        try:
            import yaml  # type: ignore[import-untyped]
        except ImportError as exc:
            raise SpecError("PyYAML is required for YAML specs: pip install pyyaml") from exc
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise SpecError(f"invalid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise SpecError("document root must be a mapping")
    return data


def resolve(spec: dict, node, _seen: frozenset = frozenset()):
    """Follow local ``$ref`` pointers (``#/...``). Unknown refs return {}."""
    if not isinstance(node, dict) or "$ref" not in node:
        return node
    ref = node["$ref"]
    if not isinstance(ref, str) or not ref.startswith("#/") or ref in _seen:
        return {}
    target = spec
    for part in ref[2:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if not isinstance(target, dict) or part not in target:
            return {}
        target = target[part]
    return resolve(spec, target, _seen | {ref})


def _finding(rule: str, severity: str, location: str, message: str) -> dict:
    return {"rule": rule, "severity": severity, "location": location, "message": message}


def lint_problem(doc, location: str = "$", http_status: int | None = None) -> list[dict]:
    """Lint one problem details object."""
    out: list[dict] = []
    if not isinstance(doc, dict):
        return [_finding("not-object", "error", location, "A problem details document must be a JSON object")]

    ptype = doc.get("type", "about:blank")
    if "type" in doc and not isinstance(doc["type"], str):
        out.append(_finding("type-string", "error", f"{location}.type", "type must be a string (URI reference)"))
    elif "type" not in doc:
        out.append(
            _finding(
                "type-missing",
                "info",
                f"{location}.type",
                "type is absent so it means about:blank; use a URI for API-specific problems",
            )
        )
    elif ptype != "about:blank" and (" " in ptype or not ptype):
        out.append(_finding("type-uri", "error", f"{location}.type", f"type '{ptype}' is not a URI reference"))
    elif ptype.startswith("http://"):
        out.append(_finding("type-https", "info", f"{location}.type", "Prefer https:// for type URIs"))

    status = doc.get("status")
    if "status" not in doc:
        out.append(
            _finding(
                "status-missing",
                "warning",
                f"{location}.status",
                "status is advisory but helps clients and logs; include it",
            )
        )
    elif not isinstance(status, int) or isinstance(status, bool) or not 100 <= status <= 599:
        out.append(
            _finding(
                "status-integer", "error", f"{location}.status", "status must be a JSON number between 100 and 599"
            )
        )
    else:
        if status < 400:
            out.append(
                _finding("status-not-error", "warning", f"{location}.status", f"status {status} is not an error status")
            )
        if http_status is not None and status != http_status:
            out.append(
                _finding(
                    "status-mismatch",
                    "error",
                    f"{location}.status",
                    f"status {status} differs from the HTTP status {http_status}",
                )
            )

    for member in ("title", "detail", "instance"):
        if member in doc and not isinstance(doc[member], str):
            out.append(_finding(f"{member}-string", "error", f"{location}.{member}", f"{member} must be a string"))
    if not doc.get("title"):
        out.append(
            _finding(
                "title-missing",
                "warning",
                f"{location}.title",
                "Add a short, human-readable title that does not change between occurrences",
            )
        )
    elif ptype == "about:blank" and isinstance(status, int) and not isinstance(status, bool):
        try:
            phrase = HTTPStatus(status).phrase
        except ValueError:
            phrase = None
        if phrase and doc["title"] != phrase:
            out.append(
                _finding(
                    "blank-title",
                    "warning",
                    f"{location}.title",
                    f"With type about:blank the title should be the status phrase '{phrase}'",
                )
            )

    detail = doc.get("detail")
    if isinstance(detail, str):
        for pattern, label in LEAK_PATTERNS:
            if pattern.search(detail):
                out.append(
                    _finding(
                        "detail-leak",
                        "error",
                        f"{location}.detail",
                        f"detail looks like it contains a {label}; never expose internals",
                    )
                )
                break

    for key, value in doc.items():
        if key in STANDARD_MEMBERS:
            continue
        if not EXTENSION_NAME.match(key):
            out.append(
                _finding(
                    "extension-name",
                    "warning",
                    f"{location}.{key}",
                    "Extension members should start with a letter, use only letters, digits "
                    "and underscores, and be at least 3 characters (RFC 9457 section 3.2)",
                )
            )
        if key == "errors" and isinstance(value, list):
            for i, item in enumerate(value):
                if isinstance(item, dict) and not ({"pointer", "detail"} & set(item)):
                    out.append(
                        _finding(
                            "errors-item",
                            "info",
                            f"{location}.errors[{i}]",
                            "Validation items should carry 'detail' and a JSON Pointer in 'pointer'",
                        )
                    )
        if isinstance(value, str):
            for pattern, label in LEAK_PATTERNS[:4]:
                if pattern.search(value):
                    out.append(
                        _finding(
                            "detail-leak", "error", f"{location}.{key}", f"member looks like it contains a {label}"
                        )
                    )
                    break
    return out


def lint_spec(spec: dict) -> list[dict]:
    """Check that error responses in an OpenAPI document use problem details."""
    out: list[dict] = []
    for path, item in (spec.get("paths") or {}).items():
        item = resolve(spec, item)
        if not isinstance(item, dict):
            continue
        for method in HTTP_METHODS:
            op = item.get(method)
            if not isinstance(op, dict):
                continue
            for code, resp in (op.get("responses") or {}).items():
                code = str(code)
                if not (code[:1] in "45" or code == "default"):
                    continue
                resp = resolve(spec, resp)
                content = (resp or {}).get("content") if isinstance(resp, dict) else None
                loc = f"{method.upper()} {path} response {code}"
                if not content:
                    out.append(
                        _finding(
                            "no-error-body",
                            "warning",
                            loc,
                            "Error response has no body; document application/problem+json",
                        )
                    )
                    continue
                if not any("problem+json" in c or "problem+xml" in c for c in content):
                    out.append(
                        _finding(
                            "not-problem-json",
                            "warning",
                            loc,
                            "Error response does not use application/problem+json; found " + ", ".join(content),
                        )
                    )
                    continue
                for ctype, media in content.items():
                    if "problem+json" not in ctype:
                        continue
                    example = (media or {}).get("example")
                    if example is None:
                        examples = (media or {}).get("examples") or {}
                        if examples:
                            first = resolve(spec, next(iter(examples.values())))
                            example = (first or {}).get("value")
                    if example is not None:
                        status = int(code) if code.isdigit() else None
                        out.extend(lint_problem(example, f"{loc} example", status))
    return out


def load_documents(path: str):
    try:
        text = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
        data = json.loads(text)
    except OSError as exc:
        raise SpecError(f"cannot read {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise SpecError(f"{path}: invalid JSON: {exc}") from exc
    return data if isinstance(data, list) else [data]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check error payloads or an OpenAPI document against RFC 9457 problem details."
    )
    sub = parser.add_subparsers(dest="mode", required=True)
    doc = sub.add_parser("doc", help="Lint captured problem+json bodies")
    doc.add_argument("files", nargs="+", help="JSON files (object or array of objects), or - for stdin")
    doc.add_argument("--status", type=int, help="HTTP status the body was returned with")
    spec = sub.add_parser("spec", help="Check error responses in an OpenAPI 3.x document")
    spec.add_argument("spec", help="openapi.yaml / openapi.json")
    for p in (doc, spec):
        p.add_argument("--format", choices=("text", "json"), default="text")
        p.add_argument("--fail-on", choices=("error", "warning", "info", "never"), default="error")
    args = parser.parse_args(argv)

    findings: list[dict] = []
    try:
        if args.mode == "doc":
            for path in args.files:
                for i, item in enumerate(load_documents(path)):
                    findings.extend(lint_problem(item, f"{path}[{i}]", args.status))
        else:
            findings = lint_spec(load_spec(args.spec))
    except SpecError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.format == "json":
        print(json.dumps({"findings": findings, "count": len(findings)}, indent=2))
    elif not findings:
        print("No findings.")
    else:
        for f in findings:
            print(f"{f['severity'].upper():8} {f['rule']:18} {f['location']}: {f['message']}")
    if args.fail_on == "never":
        return 0
    threshold = SEVERITY_RANK[args.fail_on]
    return 1 if any(SEVERITY_RANK[f["severity"]] >= threshold for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
