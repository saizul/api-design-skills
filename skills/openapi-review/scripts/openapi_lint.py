#!/usr/bin/env python3
"""Lint an OpenAPI 3.x document for documentation and design gaps.

Checks missing descriptions, operationIds, error responses, examples, security,
undeclared path parameters and inconsistent naming. Reads JSON with the standard
library; YAML needs PyYAML (``pip install pyyaml``).

Exit codes: 0 = no findings at or above --fail-on, 1 = findings, 2 = usage or
parse error.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HTTP_METHODS = ("get", "put", "post", "delete", "options", "head", "patch", "trace")
SEVERITY_RANK = {"info": 0, "warning": 1, "error": 2}
VERB_SEGMENTS = {
    "get",
    "create",
    "update",
    "delete",
    "remove",
    "add",
    "fetch",
    "list",
    "set",
    "edit",
    "save",
    "insert",
}

STYLE_LABEL = {
    "camel": "camelCase",
    "snake": "snake_case",
    "kebab": "kebab-case",
    "pascal": "PascalCase",
    "mixed": "mixed separators",
}

RULES = {
    "spec-version": "Document must declare openapi 3.x",
    "info-title": "info.title is required",
    "info-version": "info.version is required",
    "info-description": "info.description helps readers understand the API",
    "servers": "Declare at least one server URL",
    "operation-id": "Every operation needs an operationId",
    "operation-id-unique": "operationIds must be unique",
    "operation-id-style": "operationIds should use one casing style",
    "operation-summary": "Operations need a summary or description",
    "operation-tags": "Operations should have at least one tag",
    "success-response": "Operations need at least one 2xx or 3xx response",
    "error-responses": "Operations should document 4xx/5xx or default responses",
    "response-description": "Every response object requires a description",
    "parameter-description": "Parameters should have a description",
    "path-parameter-declared": "Path template variables must be declared as in: path parameters",
    "path-parameter-required": "Path parameters must be required: true",
    "get-request-body": "GET and DELETE operations should not have a request body",
    "examples": "JSON success responses and request bodies should include an example",
    "security-schemes": "Declare components.securitySchemes",
    "operation-security": "Operation has no security requirement (global or local)",
    "path-casing": "Path segments should be lowercase kebab-case",
    "path-trailing-slash": "Paths should not end with a slash",
    "path-verb": "Paths should name resources, not actions",
    "property-casing": "Schema properties should use one casing style",
    "enum-casing": "Values of one enum should use one casing style",
}

ENUM_STYLE_LABEL = {
    "lower": "a single lowercase word",
    "snake": "snake_case",
    "kebab": "kebab-case",
    "camel": "camelCase",
    "pascal": "PascalCase",
    "upper": "UPPER_SNAKE_CASE",
}


class SpecError(Exception):
    """Raised when the document cannot be read."""


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


def iter_operations(spec: dict):
    """Yield (path, method, operation, merged_parameters)."""
    paths = spec.get("paths") or {}
    if not isinstance(paths, dict):
        return
    for path, item in paths.items():
        item = resolve(spec, item)
        if not isinstance(item, dict):
            continue
        shared = [resolve(spec, p) for p in item.get("parameters") or []]
        for method in HTTP_METHODS:
            op = item.get(method)
            if not isinstance(op, dict):
                continue
            own = [resolve(spec, p) for p in op.get("parameters") or []]
            merged = {}
            for param in shared + own:
                if isinstance(param, dict):
                    merged[(param.get("name"), param.get("in"))] = param
            yield path, method, op, list(merged.values())


def casing(name: str) -> str | None:
    """Classify an identifier as camel, snake, kebab, pascal or None (single word)."""
    if not name or not re.match(r"^[A-Za-z][A-Za-z0-9_\-]*$", name):
        return None
    if "_" in name and "-" not in name and name == name.lower():
        return "snake"
    if "-" in name and "_" not in name and name == name.lower():
        return "kebab"
    if "_" in name or "-" in name:
        return "mixed"
    if name[0].isupper() and any(c.islower() for c in name):
        return "pascal"
    if any(c.isupper() for c in name[1:]):
        return "camel"
    return None


def enum_casing(value) -> str | None:
    """Classify one enum value; None for non-strings and values that are not identifiers.

    A leading ``-`` or ``+`` (sort direction, as in ``-created_at``) is ignored.
    """
    if not isinstance(value, str):
        return None
    name = value.lstrip("+-")
    if not re.match(r"^[A-Za-z][A-Za-z0-9_\-]*$", name):
        return None
    letters = [c for c in name if c.isalpha()]
    if all(c.isupper() for c in letters) and "-" not in name and (len(letters) > 1 or "_" in name):
        return "upper"
    if name == name.lower():
        if "_" in name and "-" not in name:
            return "snake"
        if "-" in name and "_" not in name:
            return "kebab"
        return "lower" if "_" not in name and "-" not in name else None
    if "_" in name or "-" in name:
        return None
    return "pascal" if name[0].isupper() else "camel"


def mixed_enum_styles(values) -> set[str]:
    """Return the casing styles of ``values`` if they are inconsistent, else an empty set.

    A single lowercase word (``paid``) fits snake_case, kebab-case and camelCase.
    """
    styles = {s for s in (enum_casing(v) for v in values) if s}
    strict = styles - {"lower"}
    if len(strict) > 1 or ("lower" in styles and strict & {"upper", "pascal"}):
        return styles
    return set()


def iter_enums(node, location: str, depth: int = 0):
    """Yield (location, enum list) for every enum in an inline schema.

    ``$ref`` is not followed: component schemas are checked under their own name.
    """
    if depth > 20 or not isinstance(node, dict) or "$ref" in node:
        return
    if isinstance(node.get("enum"), list):
        yield location, node["enum"]
    for name, prop in (node.get("properties") or {}).items():
        yield from iter_enums(prop, f"{location}.{name}", depth + 1)
    if isinstance(node.get("items"), dict):
        yield from iter_enums(node["items"], f"{location}[]", depth + 1)
    for key in ("allOf", "oneOf", "anyOf"):
        for index, sub in enumerate(node.get(key) or []):
            yield from iter_enums(sub, f"{location}.{key}[{index}]", depth + 1)


def media_has_example(spec: dict, media: dict) -> bool:
    if not isinstance(media, dict):
        return False
    if "example" in media or media.get("examples"):
        return True
    schema = resolve(spec, media.get("schema") or {})
    return _schema_has_example(spec, schema, depth=0)


def _schema_has_example(spec: dict, schema, depth: int) -> bool:
    if not isinstance(schema, dict) or depth > 6:
        return False
    if "example" in schema or schema.get("examples"):
        return True
    for key in ("allOf", "oneOf", "anyOf"):
        for sub in schema.get(key) or []:
            if _schema_has_example(spec, resolve(spec, sub), depth + 1):
                return True
    if schema.get("type") == "array":
        return _schema_has_example(spec, resolve(spec, schema.get("items") or {}), depth + 1)
    props = schema.get("properties") or {}
    if props and all(_schema_has_example(spec, resolve(spec, p), depth + 1) for p in props.values()):
        return True
    return False


def json_media(content) -> list:
    if not isinstance(content, dict):
        return []
    return [m for t, m in content.items() if "json" in t.lower()]


def lint(spec: dict) -> list[dict]:
    """Return a list of findings: {rule, severity, location, message}."""
    findings: list[dict] = []

    def add(rule: str, severity: str, location: str, message: str | None = None) -> None:
        findings.append(
            {
                "rule": rule,
                "severity": severity,
                "location": location,
                "message": message or RULES[rule],
            }
        )

    version = str(spec.get("openapi", ""))
    if not version.startswith("3."):
        add("spec-version", "error", "openapi", f"Expected openapi 3.x, found {version or 'none'}")

    info = spec.get("info") if isinstance(spec.get("info"), dict) else {}
    if not info.get("title"):
        add("info-title", "error", "info.title")
    if not info.get("version"):
        add("info-version", "error", "info.version")
    if not info.get("description"):
        add("info-description", "warning", "info.description")
    if not spec.get("servers"):
        add("servers", "info", "servers")

    components = spec.get("components") or {}
    schemes = components.get("securitySchemes") or {}
    global_security = spec.get("security")
    if not schemes:
        add("security-schemes", "warning", "components.securitySchemes")

    op_ids: dict[str, str] = {}
    id_styles: dict[str, list[str]] = {}

    enum_sites: list[tuple[str, list]] = []
    for schema_name, schema in (components.get("schemas") or {}).items():
        enum_sites.extend(iter_enums(schema, f"components.schemas.{schema_name}"))

    for path, method, op, params in iter_operations(spec):
        loc = f"{method.upper()} {path}"
        for param in params:
            enum_sites.extend(iter_enums(param.get("schema"), f"{loc} parameter {param.get('name')}"))

        op_id = op.get("operationId")
        if not op_id:
            add("operation-id", "error", loc)
        else:
            if op_id in op_ids:
                add(
                    "operation-id-unique",
                    "error",
                    loc,
                    f"operationId '{op_id}' is also used by {op_ids[op_id]}",
                )
            op_ids.setdefault(op_id, loc)
            style = casing(op_id)
            if style:
                id_styles.setdefault(style, []).append(loc)

        if not op.get("summary") and not op.get("description"):
            add("operation-summary", "warning", loc)
        if not op.get("tags"):
            add("operation-tags", "info", loc)

        # Path parameters
        template_vars = re.findall(r"{([^}/]+)}", path)
        declared = {p.get("name"): p for p in params if p.get("in") == "path"}
        for var in template_vars:
            if var not in declared:
                add(
                    "path-parameter-declared",
                    "error",
                    loc,
                    f"Path variable '{{{var}}}' has no in: path parameter",
                )
            elif declared[var].get("required") is not True:
                add(
                    "path-parameter-required",
                    "error",
                    f"{loc} parameter {var}",
                )
        for param in params:
            if not param.get("description"):
                add(
                    "parameter-description",
                    "warning",
                    f"{loc} parameter {param.get('name')} ({param.get('in')})",
                )

        # Request body
        body = resolve(spec, op.get("requestBody") or {})
        if body and method in ("get", "delete", "head"):
            add("get-request-body", "warning", loc)
        for media in json_media(body.get("content") if isinstance(body, dict) else None):
            if not media_has_example(spec, media):
                add("examples", "warning", f"{loc} requestBody", "Request body has no example")

        # Responses
        responses = op.get("responses") or {}
        codes = [str(c) for c in responses]
        if not any(c[:1] in "23" for c in codes):
            add("success-response", "error", loc)
        if not any(c[:1] in "45" or c.lower() == "default" for c in codes):
            add("error-responses", "warning", loc, "No 4xx/5xx or default response documented")
        for code, resp in responses.items():
            resp = resolve(spec, resp)
            if not isinstance(resp, dict):
                continue
            if not resp.get("description"):
                add("response-description", "error", f"{loc} response {code}")
            if str(code).startswith("2"):
                for media in json_media(resp.get("content")):
                    if not media_has_example(spec, media):
                        add(
                            "examples",
                            "warning",
                            f"{loc} response {code}",
                            "Success response has no example",
                        )

        # Security
        if schemes:
            op_security = op.get("security")
            if op_security is None and not global_security:
                add("operation-security", "warning", loc)

    # operationId casing
    if len(id_styles) > 1:
        dominant = max(id_styles, key=lambda s: len(id_styles[s]))
        for style, locs in id_styles.items():
            if style == dominant:
                continue
            for loc in locs:
                add(
                    "operation-id-style",
                    "warning",
                    loc,
                    f"operationId uses {STYLE_LABEL[style]}; most operations use {STYLE_LABEL[dominant]}",
                )

    # Path naming
    for path in (spec.get("paths") or {}).keys():
        if len(path) > 1 and path.endswith("/"):
            add("path-trailing-slash", "warning", path)
        for segment in path.strip("/").split("/"):
            if not segment or segment.startswith("{"):
                continue
            literal = segment.split(":")[0]
            if literal != literal.lower() or "_" in literal:
                add("path-casing", "warning", path, f"Segment '{segment}' is not lowercase kebab-case")
            words = [w.lower() for w in re.split(r"[-_]|(?<=[a-z0-9])(?=[A-Z])", literal) if w]
            if words and words[0] in VERB_SEGMENTS:
                add("path-verb", "warning", path, f"Segment '{segment}' looks like an action verb")

    # Property casing across component schemas
    prop_styles: dict[str, list[str]] = {}
    for schema_name, schema in (components.get("schemas") or {}).items():
        schema = resolve(spec, schema)
        if not isinstance(schema, dict):
            continue
        for prop in schema.get("properties") or {}:
            style = casing(prop)
            if style:
                prop_styles.setdefault(style, []).append(f"components.schemas.{schema_name}.{prop}")
    if len(prop_styles) > 1:
        dominant = max(prop_styles, key=lambda s: len(prop_styles[s]))
        for style, locs in prop_styles.items():
            if style == dominant:
                continue
            for loc in locs:
                add(
                    "property-casing",
                    "warning",
                    loc,
                    f"Property uses {STYLE_LABEL[style]}; most properties use {STYLE_LABEL[dominant]}",
                )

    # Enum value casing
    for location, values in enum_sites:
        styles = mixed_enum_styles(values)
        if styles:
            shown = ", ".join(ENUM_STYLE_LABEL[s] for s in sorted(styles))
            add("enum-casing", "warning", location, f"Enum values mix casing styles ({shown})")

    return findings


def format_text(findings: list[dict]) -> str:
    if not findings:
        return "No findings."
    lines = []
    for f in sorted(findings, key=lambda f: (-SEVERITY_RANK[f["severity"]], f["location"])):
        lines.append(f"{f['severity'].upper():8} {f['rule']:24} {f['location']}: {f['message']}")
    counts = {s: sum(1 for f in findings if f["severity"] == s) for s in SEVERITY_RANK}
    lines.append(
        f"\n{len(findings)} findings: {counts['error']} errors, {counts['warning']} warnings, {counts['info']} info"
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Lint an OpenAPI 3.x document (JSON or YAML) for documentation and design gaps.",
        epilog="Rules: " + ", ".join(sorted(RULES)),
    )
    parser.add_argument("spec", help="Path to openapi.yaml / openapi.json, or - for stdin")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument(
        "--fail-on",
        choices=("error", "warning", "info", "never"),
        default="error",
        help="Lowest severity that makes the exit code 1 (default: error)",
    )
    parser.add_argument("--ignore", action="append", default=[], metavar="RULE", help="Rule id to skip (repeatable)")
    parser.add_argument("--list-rules", action="store_true", help="Print rule ids and exit")
    args = parser.parse_args(argv)

    if args.list_rules:
        for rule, text in sorted(RULES.items()):
            print(f"{rule:24} {text}")
        return 0

    try:
        spec = load_spec(args.spec)
    except SpecError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    findings = [f for f in lint(spec) if f["rule"] not in set(args.ignore)]
    if args.format == "json":
        print(json.dumps({"findings": findings, "count": len(findings)}, indent=2))
    else:
        print(format_text(findings))

    if args.fail_on == "never":
        return 0
    threshold = SEVERITY_RANK[args.fail_on]
    return 1 if any(SEVERITY_RANK[f["severity"]] >= threshold for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
