#!/usr/bin/env python3
"""Generate human-readable Markdown reference docs with curl examples from OpenAPI 3.x.

Output: overview, authentication, an endpoint index grouped by tag, and for each
operation its parameters, request body, a runnable curl command, responses and
example payloads. Examples come from the spec (example/examples/default/enum) or
are synthesised from the schema. Credentials are always shell variables such as
$API_TOKEN, never literal values.

Exit codes: 0 = written, 2 = usage or parse error.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import quote

HTTP_METHODS = ("get", "put", "post", "delete", "options", "head", "patch", "trace")


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


FORMAT_EXAMPLES = {
    "date-time": "2026-01-15T09:30:00Z",
    "date": "2026-01-15",
    "time": "09:30:00",
    "email": "user@example.com",
    "uuid": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "uri": "https://example.com/resource",
    "url": "https://example.com/resource",
    "hostname": "api.example.com",
    "ipv4": "192.0.2.10",
    "ipv6": "2001:db8::10",
    "byte": "aGVsbG8=",
    "password": "********",
}


def example_for(spec: dict, schema, depth: int = 0, seen: frozenset = frozenset()):
    """Build an example value from a schema."""
    if isinstance(schema, dict) and "$ref" in schema:
        if schema["$ref"] in seen or depth > 6:
            return None
        seen = seen | {schema["$ref"]}
    schema = resolve(spec, schema)
    if not isinstance(schema, dict):
        return None
    if "example" in schema:
        return schema["example"]
    examples = schema.get("examples")
    if isinstance(examples, list) and examples:
        return examples[0]
    if "default" in schema:
        return schema["default"]
    if "const" in schema:
        return schema["const"]
    if schema.get("enum"):
        return schema["enum"][0]
    if schema.get("allOf"):
        merged: dict = {}
        for sub in schema["allOf"]:
            value = example_for(spec, sub, depth + 1, seen)
            if isinstance(value, dict):
                merged.update(value)
        if schema.get("properties"):
            value = example_for(spec, {**schema, "allOf": None}, depth + 1, seen)
            if isinstance(value, dict):
                merged.update(value)
        return merged
    for key in ("oneOf", "anyOf"):
        if schema.get(key):
            return example_for(spec, schema[key][0], depth + 1, seen)

    stype = schema.get("type")
    if isinstance(stype, list):
        stype = next((t for t in stype if t != "null"), None)
    if stype is None and "properties" in schema:
        stype = "object"
    if stype == "object":
        result = {}
        for name, prop in (schema.get("properties") or {}).items():
            result[name] = example_for(spec, prop, depth + 1, seen)
        return result
    if stype == "array":
        item = example_for(spec, schema.get("items") or {}, depth + 1, seen)
        return [] if item is None else [item]
    if stype == "integer":
        return int(schema.get("minimum", 1)) if "minimum" in schema else 1
    if stype == "number":
        return schema.get("minimum", 9.99)
    if stype == "boolean":
        return True
    if stype == "string":
        return FORMAT_EXAMPLES.get(schema.get("format", ""), "string")
    return None


def media_example(spec: dict, media: dict):
    if not isinstance(media, dict):
        return None
    if "example" in media:
        return media["example"]
    examples = media.get("examples")
    if isinstance(examples, dict) and examples:
        first = resolve(spec, next(iter(examples.values())))
        if isinstance(first, dict) and "value" in first:
            return first["value"]
    return example_for(spec, media.get("schema") or {})


def pick_media(content):
    """Prefer a JSON media type; return (content_type, media) or (None, None)."""
    if not isinstance(content, dict) or not content:
        return None, None
    for ctype, media in content.items():
        if "json" in ctype.lower():
            return ctype, media
    ctype = next(iter(content))
    return ctype, content[ctype]


def shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


def auth_parts(spec: dict, op: dict):
    """Return (headers, query, curl_flags, description) for the first security requirement."""
    security = op.get("security", spec.get("security")) or []
    schemes = (spec.get("components") or {}).get("securitySchemes") or {}
    for req in security:
        for name in req or {}:
            scheme = resolve(spec, schemes.get(name) or {})
            stype = scheme.get("type")
            if stype == "http" and str(scheme.get("scheme", "")).lower() == "bearer":
                return ["Authorization: Bearer $API_TOKEN"], [], [], name
            if stype == "http" and str(scheme.get("scheme", "")).lower() == "basic":
                return [], [], ['-u "$API_USER:$API_PASSWORD"'], name
            if stype == "apiKey":
                key_name = scheme.get("name", "X-API-Key")
                if scheme.get("in") == "header":
                    return [f"{key_name}: $API_KEY"], [], [], name
                if scheme.get("in") == "query":
                    return [], [(key_name, "$API_KEY")], [], name
                if scheme.get("in") == "cookie":
                    return [f"Cookie: {key_name}=$API_KEY"], [], [], name
            if stype in ("oauth2", "openIdConnect"):
                return ["Authorization: Bearer $ACCESS_TOKEN"], [], [], name
    return [], [], [], None


def build_curl(spec: dict, base_url: str, path: str, method: str, op: dict, params: list) -> str:
    url_path = path
    for p in params:
        if p.get("in") == "path":
            value = p.get("example", example_for(spec, p.get("schema") or {}))
            url_path = url_path.replace("{" + str(p.get("name")) + "}", quote(str(value), safe=""))
    headers, query, flags, _ = auth_parts(spec, op)
    for p in params:
        if p.get("in") == "query" and p.get("required"):
            value = p.get("example", example_for(spec, p.get("schema") or {}))
            query.append((p.get("name"), value))
        if p.get("in") == "header" and p.get("required"):
            value = p.get("example", example_for(spec, p.get("schema") or {}))
            headers.append(f"{p.get('name')}: {value}")
    query_string = "&".join(f"{quote(str(k))}={v if str(v).startswith('$') else quote(str(v))}" for k, v in query)
    url = base_url.rstrip("/") + url_path + (f"?{query_string}" if query_string else "")

    lines = [f'curl "{url}"' if method == "get" else f'curl -X {method.upper()} "{url}"']
    lines += flags
    body = resolve(spec, op.get("requestBody") or {})
    ctype, media = pick_media(body.get("content") if isinstance(body, dict) else None)
    if ctype:
        headers.append(f"Content-Type: {ctype}")
    responses = op.get("responses") or {}
    accept = None
    for code, resp in responses.items():
        if str(code).startswith("2"):
            accept, _ = pick_media(resolve(spec, resp).get("content"))
            if accept:
                break
    if accept:
        headers.insert(0, f"Accept: {accept}")
    for header in headers:
        lines.append(f'-H "{header}"')
    if ctype:
        example = media_example(spec, media)
        if "json" in ctype:
            lines.append("-d " + shell_quote(json.dumps(example, indent=2, default=str)))
        elif example is not None:
            lines.append("-d " + shell_quote(str(example)))
    return " \\\n  ".join(lines)


def md_escape(text) -> str:
    return str(text if text is not None else "").replace("|", "\\|").replace("\n", " ").strip()


def anchor(text: str) -> str:
    slug = re.sub(r"[^\w\- ]", "", text.lower()).strip().replace(" ", "-")
    return re.sub(r"-+", "-", slug)


def type_label(spec: dict, schema) -> str:
    ref = schema.get("$ref") if isinstance(schema, dict) else None
    schema = resolve(spec, schema)
    if ref:
        return ref.split("/")[-1]
    if not isinstance(schema, dict):
        return ""
    stype = schema.get("type", "")
    if isinstance(stype, list):
        stype = " | ".join(stype)
    if stype == "array":
        return f"array of {type_label(spec, schema.get('items') or {})}"
    if schema.get("format"):
        return f"{stype} ({schema['format']})"
    if schema.get("enum"):
        return f"{stype or 'enum'}: " + ", ".join(f"`{v}`" for v in schema["enum"])
    return str(stype)


def render(spec: dict, base_url: str | None = None, tags: list[str] | None = None, curl: bool = True) -> str:
    info = spec.get("info") or {}
    servers = spec.get("servers") or []
    base = base_url or (servers[0].get("url") if servers else "https://api.example.com")
    out: list[str] = [f"# {info.get('title', 'API')} reference", ""]
    if info.get("version"):
        out += [f"Version: `{info['version']}`", ""]
    if info.get("description"):
        out += [str(info["description"]).strip(), ""]
    if servers:
        out += ["## Servers", ""]
        for s in servers:
            desc = f" - {s['description']}" if s.get("description") else ""
            out.append(f"- `{s.get('url')}`{desc}")
        out.append("")

    schemes = (spec.get("components") or {}).get("securitySchemes") or {}
    if schemes:
        out += ["## Authentication", ""]
        for name, scheme in schemes.items():
            scheme = resolve(spec, scheme)
            stype = scheme.get("type")
            if stype == "http":
                how = f"HTTP `{scheme.get('scheme')}` authentication"
                if str(scheme.get("scheme", "")).lower() == "bearer":
                    how += ": send `Authorization: Bearer $API_TOKEN`"
            elif stype == "apiKey":
                how = f"API key in {scheme.get('in')} `{scheme.get('name')}`"
            elif stype == "oauth2":
                how = "OAuth 2.0 (" + ", ".join((scheme.get("flows") or {}).keys()) + ")"
            else:
                how = str(stype)
            desc = f" {scheme['description'].strip()}" if scheme.get("description") else ""
            out.append(f"- **{name}**: {how}.{desc}")
        out += ["", "Examples read credentials from environment variables; export them first.", ""]

    groups: dict[str, list] = {}
    for path, method, op, params in iter_operations(spec):
        op_tags = op.get("tags") or ["default"]
        if tags and not set(tags) & set(op_tags):
            continue
        groups.setdefault(op_tags[0], []).append((path, method, op, params))

    tag_desc = {t.get("name"): t.get("description") for t in spec.get("tags") or [] if isinstance(t, dict)}
    out += ["## Endpoints", ""]
    for tag, ops in groups.items():
        out.append(f"- **{tag}**")
        for path, method, op, _ in ops:
            title = op.get("summary") or op.get("operationId") or f"{method.upper()} {path}"
            out.append(f"  - [`{method.upper()} {path}`](#{anchor(title)}) {md_escape(title)}")
    out.append("")

    for tag, ops in groups.items():
        out += [f"## {tag}", ""]
        if tag_desc.get(tag):
            out += [str(tag_desc[tag]).strip(), ""]
        for path, method, op, params in ops:
            title = op.get("summary") or op.get("operationId") or f"{method.upper()} {path}"
            out += [f"### {title}", "", f"`{method.upper()} {path}`", ""]
            if op.get("deprecated"):
                out += ["> **Deprecated.** Avoid in new integrations.", ""]
            if op.get("description"):
                out += [str(op["description"]).strip(), ""]
            _, _, _, auth_name = auth_parts(spec, op)
            if auth_name:
                out += [f"Authentication: `{auth_name}`", ""]
            elif "security" in op or spec.get("security") is not None:
                out += ["Authentication: none", ""]

            if params:
                out += ["| Parameter | In | Type | Required | Description |", "| --- | --- | --- | --- | --- |"]
                for p in params:
                    out.append(
                        f"| `{md_escape(p.get('name'))}` | {p.get('in')} | "
                        f"{md_escape(type_label(spec, p.get('schema') or {}))} | "
                        f"{'yes' if p.get('required') else 'no'} | {md_escape(p.get('description'))} |"
                    )
                out.append("")

            body = resolve(spec, op.get("requestBody") or {})
            ctype, media = pick_media(body.get("content") if isinstance(body, dict) else None)
            if ctype:
                out += [f"**Request body** (`{ctype}`{', required' if body.get('required') else ''})", ""]
                schema = resolve(spec, (media or {}).get("schema") or {})
                props = schema.get("properties") if isinstance(schema, dict) else None
                if props:
                    required = set(schema.get("required") or [])
                    out += ["| Field | Type | Required | Description |", "| --- | --- | --- | --- |"]
                    for name, prop in props.items():
                        resolved = resolve(spec, prop)
                        if isinstance(resolved, dict) and resolved.get("readOnly"):
                            continue
                        out.append(
                            f"| `{name}` | {md_escape(type_label(spec, prop))} | "
                            f"{'yes' if name in required else 'no'} | "
                            f"{md_escape((resolved or {}).get('description'))} |"
                        )
                    out.append("")

            if curl:
                out += [
                    "**Example request**",
                    "",
                    "```bash",
                    build_curl(spec, base, path, method, op, params),
                    "```",
                    "",
                ]

            responses = op.get("responses") or {}
            if responses:
                out += ["**Responses**", "", "| Status | Description |", "| --- | --- |"]
                for code, resp in responses.items():
                    out.append(f"| `{code}` | {md_escape(resolve(spec, resp).get('description'))} |")
                out.append("")
                for code, resp in responses.items():
                    if not str(code).startswith("2"):
                        continue
                    rtype, rmedia = pick_media(resolve(spec, resp).get("content"))
                    if rtype and "json" in rtype:
                        example = media_example(spec, rmedia)
                        out += [
                            f"**Example response** (`{code}`)",
                            "",
                            "```json",
                            json.dumps(example, indent=2, default=str),
                            "```",
                            "",
                        ]
                        break
    return "\n".join(out).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate Markdown API reference docs with curl examples from an OpenAPI 3.x document."
    )
    parser.add_argument("spec", help="Path to openapi.yaml / openapi.json, or - for stdin")
    parser.add_argument("-o", "--output", help="Write Markdown to this file (default: stdout)")
    parser.add_argument("--base-url", help="Base URL for curl examples (default: first server)")
    parser.add_argument("--tag", action="append", default=[], help="Only document this tag (repeatable)")
    parser.add_argument("--no-curl", action="store_true", help="Omit curl examples")
    parser.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="json prints {operations: [{method, path, curl}]} for reuse",
    )
    args = parser.parse_args(argv)

    try:
        spec = load_spec(args.spec)
    except SpecError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.format == "json":
        servers = spec.get("servers") or []
        base = args.base_url or (servers[0].get("url") if servers else "https://api.example.com")
        ops = [
            {
                "method": method.upper(),
                "path": path,
                "operationId": op.get("operationId"),
                "summary": op.get("summary"),
                "curl": build_curl(spec, base, path, method, op, params),
            }
            for path, method, op, params in iter_operations(spec)
            if not args.tag or set(args.tag) & set(op.get("tags") or ["default"])
        ]
        text = json.dumps({"operations": ops}, indent=2) + "\n"
    else:
        text = render(spec, args.base_url, args.tag or None, curl=not args.no_curl)

    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"wrote {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
