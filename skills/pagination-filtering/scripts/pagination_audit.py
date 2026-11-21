#!/usr/bin/env python3
"""Audit collection endpoints in an OpenAPI 3.x document for pagination, sorting and filtering.

Finds GET operations that return lists and reports: no pagination, page size
without a maximum or default, bare top-level arrays, no way to reach the next
page, and inconsistent parameter names across the API (page/per_page vs
limit/offset vs cursor, sort vs order_by).

Exit codes: 0 = no findings at or above --fail-on, 1 = findings, 2 = usage or
parse error.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HTTP_METHODS = ("get", "put", "post", "delete", "options", "head", "patch", "trace")
SEVERITY_RANK = {"info": 0, "warning": 1, "error": 2}

SIZE_PARAMS = {
    "limit",
    "page_size",
    "pagesize",
    "per_page",
    "perpage",
    "size",
    "first",
    "top",
    "max_results",
    "maxresults",
    "page[size]",
    "page[limit]",
}
CURSOR_PARAMS = {
    "cursor",
    "after",
    "before",
    "page_token",
    "pagetoken",
    "next_token",
    "nexttoken",
    "starting_after",
    "ending_before",
    "continuation_token",
    "page[after]",
    "page[cursor]",
    "page[before]",
}
OFFSET_PARAMS = {"offset", "skip", "start", "page[offset]"}
PAGE_PARAMS = {"page", "page_number", "pagenumber", "page[number]"}
SORT_PARAMS = {"sort", "sort_by", "sortby", "order", "order_by", "orderby", "ordering"}
NEXT_FIELDS = {
    "next",
    "next_cursor",
    "nextcursor",
    "next_page_token",
    "nextpagetoken",
    "cursor",
    "has_more",
    "hasmore",
    "links",
    "_links",
    "next_page",
    "nextpage",
    "page_info",
    "pageinfo",
    "meta",
    "continuation_token",
}
LIST_KEYS = ("data", "items", "results", "records", "entries", "edges", "nodes", "content")


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


def flatten(spec: dict, schema) -> dict:
    """Merge allOf members into one object schema (shallow)."""
    schema = resolve(spec, schema)
    if not isinstance(schema, dict):
        return {}
    if not schema.get("allOf"):
        return schema
    merged = {"type": "object", "properties": {}}
    for sub in schema["allOf"]:
        sub = flatten(spec, sub)
        merged["properties"].update(sub.get("properties") or {})
    merged["properties"].update(schema.get("properties") or {})
    return merged


def collection_shape(spec: dict, op: dict):
    """Return ('array'|'envelope'|None, response_schema, response_headers)."""
    for code, resp in (op.get("responses") or {}).items():
        if str(code) not in ("200", "206"):
            continue
        resp = resolve(spec, resp)
        if not isinstance(resp, dict):
            continue
        headers = {k.lower() for k in (resp.get("headers") or {})}
        for ctype, media in (resp.get("content") or {}).items():
            if "json" not in ctype:
                continue
            schema = flatten(spec, (media or {}).get("schema") or {})
            if schema.get("type") == "array":
                return "array", schema, headers
            props = schema.get("properties") or {}
            for key in LIST_KEYS:
                if resolve(spec, props.get(key) or {}).get("type") == "array":
                    return "envelope", schema, headers
    return None, None, set()


def style_of(names: set[str]) -> str | None:
    if names & CURSOR_PARAMS:
        return "cursor"
    if names & PAGE_PARAMS:
        return "page"
    if names & OFFSET_PARAMS:
        return "offset"
    return None


def audit(spec: dict) -> list[dict]:
    findings: list[dict] = []

    def add(rule: str, severity: str, location: str, message: str) -> None:
        findings.append({"rule": rule, "severity": severity, "location": location, "message": message})

    styles: dict[str, list[str]] = {}
    size_names: dict[str, list[str]] = {}
    sort_names: dict[str, list[str]] = {}
    collections = 0

    for path, method, op, params in iter_operations(spec):
        if method != "get":
            continue
        shape, schema, headers = collection_shape(spec, op)
        single_resource = path.rstrip("/").endswith("}") and shape == "envelope"
        if not shape or single_resource:
            continue
        collections += 1
        loc = f"GET {path}"
        query = {str(p.get("name", "")).lower(): p for p in params if p.get("in") == "query"}
        names = set(query)

        style = style_of(names)
        size = names & SIZE_PARAMS
        if not style and not size:
            add(
                "no-pagination",
                "warning",
                loc,
                "Returns a list but has no pagination parameters; add limit + cursor before clients depend on it",
            )
        if style:
            styles.setdefault(style, []).append(loc)
        for name in size:
            size_names.setdefault(name, []).append(loc)
            p_schema = resolve(spec, query[name].get("schema") or {})
            if "maximum" not in p_schema:
                add(
                    "page-size-maximum",
                    "warning",
                    f"{loc} parameter {name}",
                    "Page size has no maximum; cap it (for example 100) and document the cap",
                )
            if "default" not in p_schema:
                add(
                    "page-size-default",
                    "info",
                    f"{loc} parameter {name}",
                    "Page size has no default; document what clients get when they omit it",
                )
        if style and not size:
            add("no-page-size", "info", loc, "Pagination without a page-size parameter; document the fixed size")
        if style == "offset":
            add(
                "offset-pagination",
                "info",
                loc,
                "Offset pagination skips or repeats rows when data changes and gets slow on deep pages; "
                "prefer cursor pagination for large or fast-changing collections",
            )

        if shape == "array":
            add(
                "top-level-array",
                "warning",
                loc,
                "Response is a bare array; an envelope ({data, next_cursor}) lets you add paging metadata later",
            )
            if style and "link" not in headers:
                add(
                    "no-next-link",
                    "warning",
                    loc,
                    "Bare array with pagination but no Link response header; clients cannot find the next page",
                )
        elif style:
            props = {k.lower() for k in (schema.get("properties") or {})}
            if not (props & NEXT_FIELDS) and "link" not in headers:
                add(
                    "no-next-link",
                    "warning",
                    loc,
                    "No next cursor/link field and no Link header; return how to fetch the next page",
                )

        for name in names & SORT_PARAMS:
            sort_names.setdefault(name, []).append(loc)
        for name, p in query.items():
            p_schema = resolve(spec, p.get("schema") or {})
            if (
                name in SORT_PARAMS
                and p_schema.get("type") == "string"
                and not (p_schema.get("enum") or p_schema.get("pattern"))
            ):
                add(
                    "sort-allowlist",
                    "info",
                    f"{loc} parameter {name}",
                    "Sort parameter accepts any string; restrict to an enum of indexed fields",
                )

    if len(styles) > 1:
        detail = "; ".join(f"{s}: {len(v)} endpoint(s)" for s, v in sorted(styles.items()))
        add("mixed-pagination-styles", "warning", "paths", f"API mixes pagination styles ({detail})")
    if len(size_names) > 1:
        add(
            "mixed-page-size-names",
            "warning",
            "paths",
            "Page size parameter has several names: " + ", ".join(sorted(size_names)),
        )
    if len(sort_names) > 1:
        add(
            "mixed-sort-names", "warning", "paths", "Sort parameter has several names: " + ", ".join(sorted(sort_names))
        )
    if collections == 0:
        add("no-collections", "info", "paths", "No GET operation returns a list; nothing to audit")
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit list endpoints in an OpenAPI 3.x document for pagination, sorting and filtering."
    )
    parser.add_argument("spec", help="Path to openapi.yaml / openapi.json, or - for stdin")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument(
        "--fail-on",
        choices=("error", "warning", "info", "never"),
        default="warning",
        help="Lowest severity that makes the exit code 1 (default: warning)",
    )
    args = parser.parse_args(argv)
    try:
        spec = load_spec(args.spec)
    except SpecError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    findings = audit(spec)
    if args.format == "json":
        print(json.dumps({"findings": findings, "count": len(findings)}, indent=2))
    elif not findings:
        print("No findings.")
    else:
        for f in findings:
            print(f"{f['severity'].upper():8} {f['rule']:24} {f['location']}: {f['message']}")
    if args.fail_on == "never":
        return 0
    threshold = SEVERITY_RANK[args.fail_on]
    return 1 if any(SEVERITY_RANK[f["severity"]] >= threshold for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
