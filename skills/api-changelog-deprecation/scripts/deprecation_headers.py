#!/usr/bin/env python3
"""Build and check HTTP deprecation signals: Deprecation (RFC 9745), Sunset (RFC 8594) and Link.

Subcommands
  headers   Print the response headers for a deprecated endpoint.
              --deprecated 2026-03-01 --sunset 2026-09-01 --link https://...
  parse     Parse Deprecation / Sunset header values and report their dates.
  check     Check an OpenAPI 3.x document: every deprecated operation or
            parameter should name a replacement, carry a sunset date
            (x-sunset) and document the Deprecation/Sunset response headers.

Exit codes: 0 = ok, 1 = findings or invalid input, 2 = usage or parse error.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from email.utils import format_datetime, parsedate_to_datetime
from pathlib import Path

HTTP_METHODS = ("get", "put", "post", "delete", "options", "head", "patch", "trace")
SEVERITY_RANK = {"info": 0, "warning": 1, "error": 2}
REPLACEMENT_HINT = re.compile(r"\b(use|replaced by|instead|migrate|superseded|successor)\b", re.I)


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


def parse_when(value) -> datetime:
    """Parse YYYY-MM-DD, ISO 8601 date-time, an HTTP-date or @unix into an aware UTC datetime."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    text = str(value).strip()
    if text.startswith("@") and text[1:].lstrip("-").isdigit():
        return datetime.fromtimestamp(int(text[1:]), tz=timezone.utc)
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    try:
        parsed = parsedate_to_datetime(text)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"cannot parse date '{text}'") from exc
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def deprecation_value(when: datetime) -> str:
    """RFC 9745 Deprecation header: a structured-field Date (@ + Unix seconds)."""
    return f"@{int(when.timestamp())}"


def sunset_value(when: datetime) -> str:
    """RFC 8594 Sunset header: an IMF-fixdate HTTP-date."""
    return format_datetime(when.astimezone(timezone.utc), usegmt=True)


def build_headers(
    deprecated: datetime,
    sunset: datetime | None = None,
    link: str | None = None,
    sunset_link: str | None = None,
    min_notice_days: int = 90,
) -> tuple[dict, list[str]]:
    """Return (headers, warnings)."""
    warnings: list[str] = []
    headers = {"Deprecation": deprecation_value(deprecated)}
    links = []
    if link:
        links.append(f'<{link}>; rel="deprecation"; type="text/html"')
    if sunset:
        if sunset <= deprecated:
            raise ValueError("sunset must be later than the deprecation date (RFC 9745 section 5)")
        if sunset - deprecated < timedelta(days=min_notice_days):
            warnings.append(
                f"only {(sunset - deprecated).days} days between deprecation and sunset; "
                f"aim for at least {min_notice_days}"
            )
        headers["Sunset"] = sunset_value(sunset)
        if sunset_link:
            links.append(f'<{sunset_link}>; rel="sunset"; type="text/html"')
    else:
        warnings.append("no sunset date: clients cannot plan the migration")
    if not link:
        warnings.append('no Link rel="deprecation": point clients at the migration guide')
    if links:
        headers["Link"] = ", ".join(links)
    return headers, warnings


def check_spec(spec: dict, today: datetime | None = None) -> list[dict]:
    today = today or datetime.now(timezone.utc)
    findings: list[dict] = []

    def add(rule: str, severity: str, location: str, message: str) -> None:
        findings.append({"rule": rule, "severity": severity, "location": location, "message": message})

    for path, method, op, params in iter_operations(spec):
        loc = f"{method.upper()} {path}"
        if op.get("deprecated"):
            text = f"{op.get('summary', '')} {op.get('description', '')}"
            if not REPLACEMENT_HINT.search(text):
                add("no-replacement", "warning", loc, "Deprecated operation does not say what to use instead")
            sunset = op.get("x-sunset")
            if not sunset:
                add("no-sunset-date", "warning", loc, "Deprecated operation has no x-sunset date")
            else:
                try:
                    when = parse_when(sunset)
                    if when < today:
                        add(
                            "past-sunset",
                            "error",
                            loc,
                            f"x-sunset {sunset} is in the past: remove the operation or return 410 Gone",
                        )
                except ValueError as exc:
                    add("bad-sunset-date", "error", loc, str(exc))
            documented = set()
            for resp in (op.get("responses") or {}).values():
                resp = resolve(spec, resp)
                if isinstance(resp, dict):
                    documented |= {h.lower() for h in resp.get("headers") or {}}
            for header in ("deprecation", "sunset"):
                if header not in documented:
                    add(
                        f"no-{header}-header",
                        "info",
                        loc,
                        f"Responses do not document the {header.capitalize()} header",
                    )
        for p in params:
            if p.get("deprecated") and not REPLACEMENT_HINT.search(str(p.get("description", ""))):
                add(
                    "param-no-replacement",
                    "warning",
                    f"{loc} parameter {p.get('name')}",
                    "Deprecated parameter does not say what to use instead",
                )
    for name, schema in ((spec.get("components") or {}).get("schemas") or {}).items():
        schema = resolve(spec, schema)
        for prop, pschema in ((schema or {}).get("properties") or {}).items():
            pschema = resolve(spec, pschema)
            if (
                isinstance(pschema, dict)
                and pschema.get("deprecated")
                and not REPLACEMENT_HINT.search(str(pschema.get("description", "")))
            ):
                add(
                    "field-no-replacement",
                    "warning",
                    f"components.schemas.{name}.{prop}",
                    "Deprecated field does not say what to use instead",
                )
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build and check Deprecation (RFC 9745) / Sunset (RFC 8594) signals.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    h = sub.add_parser("headers", help="Print deprecation response headers")
    h.add_argument("--deprecated", required=True, help="When the endpoint is/was deprecated (YYYY-MM-DD or ISO)")
    h.add_argument("--sunset", help="When it stops working (YYYY-MM-DD or ISO)")
    h.add_argument("--link", help='Migration guide URL for Link rel="deprecation"')
    h.add_argument("--sunset-link", help='Policy URL for Link rel="sunset"')
    h.add_argument("--min-notice-days", type=int, default=90)
    h.add_argument("--format", choices=("text", "json", "nginx"), default="text")

    p = sub.add_parser("parse", help="Parse header values")
    p.add_argument("--deprecation", help='Deprecation header value, e.g. "@1688169599"')
    p.add_argument("--sunset", help='Sunset header value, e.g. "Sun, 30 Jun 2024 23:59:59 GMT"')

    c = sub.add_parser("check", help="Check deprecations in an OpenAPI 3.x document")
    c.add_argument("spec")
    c.add_argument("--today", help=argparse.SUPPRESS)
    c.add_argument("--format", choices=("text", "json"), default="text")
    c.add_argument("--fail-on", choices=("error", "warning", "info", "never"), default="warning")
    args = parser.parse_args(argv)

    if args.command == "headers":
        try:
            deprecated = parse_when(args.deprecated)
            sunset = parse_when(args.sunset) if args.sunset else None
            headers, warnings = build_headers(deprecated, sunset, args.link, args.sunset_link, args.min_notice_days)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        if args.format == "json":
            print(json.dumps({"headers": headers, "warnings": warnings}, indent=2))
        else:
            for key, value in headers.items():
                if args.format == "nginx":
                    print(f"add_header {key} '{value}' always;")
                else:
                    print(f"{key}: {value}")
            for w in warnings:
                print(f"warning: {w}", file=sys.stderr)
        return 0

    if args.command == "parse":
        result = {}
        try:
            if args.deprecation:
                value = args.deprecation.strip()
                if not re.fullmatch(r"@-?\d+", value):
                    raise ValueError("Deprecation must be a structured-field Date like @1688169599 (RFC 9745)")
                result["deprecation"] = parse_when(value).isoformat()
            if args.sunset:
                result["sunset"] = parse_when(args.sunset).isoformat()
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(result, indent=2))
        return 0

    try:
        spec = load_spec(args.spec)
    except SpecError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    today = parse_when(args.today) if args.today else None
    findings = check_spec(spec, today)
    if args.format == "json":
        print(json.dumps({"findings": findings, "count": len(findings)}, indent=2))
    elif not findings:
        print("No findings.")
    else:
        for f in findings:
            print(f"{f['severity'].upper():8} {f['rule']:22} {f['location']}: {f['message']}")
    if args.fail_on == "never":
        return 0
    threshold = SEVERITY_RANK[args.fail_on]
    return 1 if any(SEVERITY_RANK[f["severity"]] >= threshold for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
