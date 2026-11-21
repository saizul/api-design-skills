#!/usr/bin/env python3
"""Scan an OpenAPI 3.x document for risks mapped to the OWASP API Security Top 10 (2023).

A spec can only show some risks. The scan flags what the contract reveals
(missing auth, unbounded inputs, sensitive fields, SSRF-prone URL inputs,
inventory problems) and lists endpoints whose code must be reviewed by hand
(object-level and function-level authorization). Read-only; no network.

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
WRITE_METHODS = {"post", "put", "patch"}

OWASP = {
    "API1": "Broken Object Level Authorization",
    "API2": "Broken Authentication",
    "API3": "Broken Object Property Level Authorization",
    "API4": "Unrestricted Resource Consumption",
    "API5": "Broken Function Level Authorization",
    "API6": "Unrestricted Access to Sensitive Business Flows",
    "API7": "Server Side Request Forgery",
    "API8": "Security Misconfiguration",
    "API9": "Improper Inventory Management",
    "API10": "Unsafe Consumption of APIs",
}

SENSITIVE_PROPERTY = re.compile(
    r"(^|_|-)(password|passwd|secret|private_?key|api_?key|access_?token|refresh_?token|"
    r"ssn|card_?number|cvv|pin)($|_|-)|(password|secret|apiKey|accessToken|refreshToken|"
    r"privateKey|cardNumber)$",
    re.IGNORECASE,
)
URL_INPUT = re.compile(
    r"(^|_|-)(url|uri|callback|webhook|redirect|endpoint|image_?url|avatar_?url|feed)"
    r"($|_|-)|(Url|Uri|Callback|Webhook|Redirect)$",
)
PRIVILEGED_PATH = re.compile(r"/(admin|internal|debug|ops|management|actuator|_)(/|$)", re.I)
LIMIT_PARAM = re.compile(r"^(limit|page_?size|per_?page|pagesize|perpage|size|first|top|count)$", re.I)
NON_PROD_SERVER = re.compile(r"(staging|stage|dev|test|qa|sandbox|uat|preview|localhost|127\.0\.0\.1)", re.I)


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


def walk_schema(spec: dict, schema, prefix: str = "", depth: int = 0, seen=None):
    """Yield (dotted_name, schema) for every property reachable from schema."""
    seen = set() if seen is None else seen
    if isinstance(schema, dict) and "$ref" in schema:
        ref = schema["$ref"]
        if ref in seen:
            return
        seen = seen | {ref}
    schema = resolve(spec, schema)
    if not isinstance(schema, dict) or depth > 8:
        return
    for key in ("allOf", "oneOf", "anyOf"):
        for sub in schema.get(key) or []:
            yield from walk_schema(spec, sub, prefix, depth + 1, seen)
    if schema.get("type") == "array" or "items" in schema:
        yield from walk_schema(spec, schema.get("items") or {}, prefix + "[]", depth + 1, seen)
    for name, prop in (schema.get("properties") or {}).items():
        full = f"{prefix}.{name}" if prefix else name
        resolved = resolve(spec, prop)
        yield full, resolved if isinstance(resolved, dict) else {}
        yield from walk_schema(spec, prop, full, depth + 1, seen)


def effective_security(spec: dict, op: dict):
    """Return the list of security requirements that apply to an operation."""
    if "security" in op:
        return op.get("security") or []
    return spec.get("security") or []


def scan(spec: dict) -> list[dict]:
    findings: list[dict] = []

    def add(owasp: str, rule: str, severity: str, location: str, message: str) -> None:
        findings.append(
            {
                "owasp": owasp,
                "category": OWASP[owasp],
                "rule": rule,
                "severity": severity,
                "location": location,
                "message": message,
            }
        )

    components = spec.get("components") or {}
    schemes = {k: resolve(spec, v) for k, v in (components.get("securitySchemes") or {}).items()}

    # API2: authentication schemes
    if not schemes:
        add(
            "API2",
            "no-security-schemes",
            "error",
            "components.securitySchemes",
            "No security schemes declared; every endpoint is anonymous",
        )
    for name, scheme in schemes.items():
        if not isinstance(scheme, dict):
            continue
        loc = f"components.securitySchemes.{name}"
        stype = scheme.get("type")
        if stype == "apiKey" and scheme.get("in") == "query":
            add(
                "API2",
                "api-key-in-query",
                "error",
                loc,
                "API key in the query string leaks into logs, proxies and browser history; use a header",
            )
        if stype == "http" and str(scheme.get("scheme", "")).lower() == "basic":
            add(
                "API2",
                "basic-auth",
                "warning",
                loc,
                "HTTP Basic sends a reusable credential on every request; prefer tokens with expiry",
            )
        if stype == "oauth2":
            flows = scheme.get("flows") or {}
            if "implicit" in flows:
                add(
                    "API2",
                    "oauth-implicit",
                    "error",
                    loc,
                    "OAuth implicit flow is deprecated (OAuth 2.0 Security BCP); use authorization code + PKCE",
                )
            if "password" in flows:
                add(
                    "API2",
                    "oauth-password",
                    "warning",
                    loc,
                    "Resource owner password flow exposes user credentials to the client",
                )

    # API8: transport
    for i, server in enumerate(spec.get("servers") or []):
        url = str((server or {}).get("url", ""))
        if url.startswith("http://") and not re.match(r"http://(localhost|127\.0\.0\.1|\[::1\])", url):
            add("API8", "plain-http-server", "error", f"servers[{i}]", f"Server {url} is not HTTPS")

    # API9: inventory
    servers = [str((s or {}).get("url", "")) for s in spec.get("servers") or []]
    non_prod = [u for u in servers if NON_PROD_SERVER.search(u)]
    if non_prod and len(non_prod) < len(servers):
        add(
            "API9",
            "mixed-environments",
            "warning",
            "servers",
            "Production and non-production servers in one document: " + ", ".join(non_prod),
        )
    if not (spec.get("info") or {}).get("version"):
        add("API9", "no-version", "warning", "info.version", "API version is not declared")

    for path, method, op, params in iter_operations(spec):
        loc = f"{method.upper()} {path}"
        security = effective_security(spec, op)
        is_public = security == [] or all(req == {} for req in security)
        responses = {str(k): v for k, v in (op.get("responses") or {}).items()}

        # API2 / API5: unauthenticated operations
        if schemes and is_public:
            explicit = "security" in op
            writes = method in WRITE_METHODS | {"delete"}
            sev = ("warning" if writes else "info") if explicit else ("error" if writes else "warning")
            add(
                "API2",
                "unauthenticated-operation",
                sev,
                loc,
                "Operation has no security requirement; confirm it is meant to be public",
            )

        if PRIVILEGED_PATH.search(path):
            add(
                "API5",
                "privileged-path",
                "warning" if not is_public else "error",
                loc,
                "Administrative/internal endpoint: verify role checks in code and keep it off public gateways",
            )

        # API5: write operations with OAuth but no scopes
        if method in WRITE_METHODS | {"delete"} and not is_public:
            for req in security:
                for scheme_name, scopes in (req or {}).items():
                    scheme = schemes.get(scheme_name) or {}
                    if scheme.get("type") in ("oauth2", "openIdConnect") and not scopes:
                        add(
                            "API5",
                            "write-without-scope",
                            "warning",
                            loc,
                            f"Write operation accepts any '{scheme_name}' token; require a specific scope",
                        )

        # API1: object-level authorization needs code review
        id_params = [p for p in params if p.get("in") == "path"]
        if id_params:
            names = ", ".join(p.get("name", "?") for p in id_params)
            add(
                "API1",
                "object-access-review",
                "info",
                loc,
                f"Accesses objects by {names}: verify the caller owns or may access each object",
            )
            for p in id_params:
                schema = resolve(spec, p.get("schema") or {})
                if isinstance(schema, dict) and schema.get("type") == "integer":
                    add(
                        "API1",
                        "sequential-id",
                        "info",
                        f"{loc} parameter {p.get('name')}",
                        "Integer IDs are guessable; authorization must not rely on obscurity (consider UUIDs)",
                    )

        # API8: auth responses
        if not is_public and not ({"401", "403"} & set(responses)) and "default" not in responses:
            add("API8", "auth-responses", "info", loc, "Secured operation does not document 401/403")

        # API4: resource consumption
        if method == "get":
            for p in params:
                if p.get("in") == "query" and LIMIT_PARAM.match(str(p.get("name", ""))):
                    schema = resolve(spec, p.get("schema") or {})
                    if not isinstance(schema, dict) or "maximum" not in schema:
                        add(
                            "API4",
                            "unbounded-page-size",
                            "warning",
                            f"{loc} parameter {p.get('name')}",
                            "Page size has no maximum; clients can request unbounded result sets",
                        )
        if "429" not in responses:
            add("API4", "no-rate-limit-response", "info", loc, "No 429 Too Many Requests response documented")
        for p in params:
            schema = resolve(spec, p.get("schema") or {})
            if (
                isinstance(schema, dict)
                and schema.get("type") == "string"
                and not ("maxLength" in schema or "enum" in schema or "format" in schema or "pattern" in schema)
            ):
                add(
                    "API4",
                    "unbounded-string-parameter",
                    "info",
                    f"{loc} parameter {p.get('name')}",
                    "String parameter has no maxLength, enum, format or pattern",
                )
            if URL_INPUT.search(str(p.get("name", ""))):
                add(
                    "API7",
                    "url-input",
                    "warning",
                    f"{loc} parameter {p.get('name')}",
                    "Accepts a URL: validate scheme/host against an allowlist and block internal addresses",
                )

        body = resolve(spec, op.get("requestBody") or {})
        if isinstance(body, dict):
            for ctype, media in (body.get("content") or {}).items():
                schema = (media or {}).get("schema") or {}
                root = resolve(spec, schema)
                if (
                    method in WRITE_METHODS
                    and "json" in ctype
                    and isinstance(root, dict)
                    and root.get("properties")
                    and root.get("additionalProperties") is not False
                ):
                    add(
                        "API3",
                        "open-request-schema",
                        "warning",
                        f"{loc} requestBody",
                        "Request schema allows unknown properties (mass assignment risk); "
                        "set additionalProperties: false or bind only allowed fields",
                    )
                for name, prop in walk_schema(spec, schema):
                    leaf = name.split(".")[-1].rstrip("[]")
                    if prop.get("readOnly") and method in WRITE_METHODS:
                        continue
                    if prop.get("type") == "string" and not ({"maxLength", "enum", "format", "pattern"} & set(prop)):
                        add(
                            "API4",
                            "unbounded-string-property",
                            "info",
                            f"{loc} requestBody {name}",
                            "String property has no maxLength, enum, format or pattern",
                        )
                    if prop.get("type") == "array" and "maxItems" not in prop:
                        add("API4", "unbounded-array", "warning", f"{loc} requestBody {name}", "Array has no maxItems")
                    if URL_INPUT.search(leaf) or prop.get("format") in ("uri", "url"):
                        add(
                            "API7",
                            "url-input",
                            "warning",
                            f"{loc} requestBody {name}",
                            "Accepts a URL: validate scheme/host against an allowlist and block internal addresses",
                        )

        # API3: sensitive data in responses
        for code, resp in responses.items():
            if not code.startswith("2"):
                continue
            resp = resolve(spec, resp)
            if not isinstance(resp, dict):
                continue
            for media in (resp.get("content") or {}).values():
                for name, prop in walk_schema(spec, (media or {}).get("schema") or {}):
                    leaf = name.split(".")[-1].rstrip("[]")
                    if SENSITIVE_PROPERTY.search(leaf) and not prop.get("writeOnly"):
                        add(
                            "API3",
                            "sensitive-response-field",
                            "error",
                            f"{loc} response {code} {name}",
                            "Response exposes a sensitive field; remove it or mark writeOnly",
                        )

        # API9: deprecated without sunset
        if op.get("deprecated") and not (op.get("x-sunset") or "sunset" in json.dumps(op).lower()):
            add(
                "API9",
                "deprecated-without-sunset",
                "info",
                loc,
                "Deprecated operation has no Sunset header or x-sunset date",
            )

    return findings


def format_text(findings: list[dict]) -> str:
    if not findings:
        return "No findings."
    lines = []
    order = sorted(findings, key=lambda f: (int(f["owasp"][3:]), -SEVERITY_RANK[f["severity"]], f["location"]))
    current = None
    for f in order:
        if f["owasp"] != current:
            current = f["owasp"]
            lines.append(f"\n{current} {f['category']}")
        lines.append(f"  {f['severity'].upper():8} {f['rule']:28} {f['location']}: {f['message']}")
    counts = {s: sum(1 for f in findings if f["severity"] == s) for s in SEVERITY_RANK}
    lines.append(
        f"\n{len(findings)} findings: {counts['error']} errors, {counts['warning']} warnings, "
        f"{counts['info']} info. API6 and API10 need a manual review (see references/owasp-api-top10.md)."
    )
    return "\n".join(lines).lstrip("\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Scan an OpenAPI 3.x document for OWASP API Security Top 10 (2023) risks.",
    )
    parser.add_argument("spec", help="Path to openapi.yaml / openapi.json, or - for stdin")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument(
        "--fail-on",
        choices=("error", "warning", "info", "never"),
        default="error",
        help="Lowest severity that makes the exit code 1 (default: error)",
    )
    parser.add_argument(
        "--min-severity", choices=("info", "warning", "error"), default="info", help="Hide findings below this severity"
    )
    parser.add_argument("--ignore", action="append", default=[], metavar="RULE", help="Rule id to skip (repeatable)")
    args = parser.parse_args(argv)

    try:
        spec = load_spec(args.spec)
    except SpecError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    floor = SEVERITY_RANK[args.min_severity]
    findings = [f for f in scan(spec) if f["rule"] not in set(args.ignore) and SEVERITY_RANK[f["severity"]] >= floor]
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
