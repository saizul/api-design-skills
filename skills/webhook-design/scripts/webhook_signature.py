#!/usr/bin/env python3
"""Sign and verify webhook payloads (Standard Webhooks, GitHub, Stripe, plain HMAC-SHA256).

Use it to test a receiver, debug a failing signature or produce fixtures. The
secret is read from an environment variable (--secret-env, default
WEBHOOK_SECRET) or a file (--secret-file), never from a command-line argument,
and it is never printed.

Schemes
  standard  Standard Webhooks: headers webhook-id, webhook-timestamp,
            webhook-signature "v1,<base64>"; signs "{id}.{timestamp}.{body}";
            secret "whsec_<base64>".
  github    X-Hub-Signature-256: "sha256=<hex>" over the raw body.
  stripe    Stripe-Signature: "t=<ts>,v1=<hex>" over "{t}.{body}".
  hmac      Hex HMAC-SHA256 over "{timestamp}.{body}" (or the body alone if no
            timestamp is given).

Exit codes: 0 = signed / valid, 1 = invalid signature, 2 = usage error.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import sys
import time
from pathlib import Path

DEFAULT_TOLERANCE = 300


class VerificationError(Exception):
    """Raised when a signature does not verify."""


def _hmac(key: bytes, message: bytes) -> bytes:
    return hmac.new(key, message, hashlib.sha256).digest()


def standard_key(secret: str) -> bytes:
    """Decode a Standard Webhooks secret (``whsec_`` + base64)."""
    raw = secret[len("whsec_") :] if secret.startswith("whsec_") else secret
    try:
        return base64.b64decode(raw, validate=True)
    except ValueError as exc:
        raise ValueError("Standard Webhooks secret must be base64 (optionally prefixed whsec_)") from exc


def check_timestamp(timestamp: int, tolerance: int, now: int | None) -> None:
    now = int(time.time()) if now is None else now
    if tolerance >= 0 and abs(now - timestamp) > tolerance:
        raise VerificationError(f"timestamp outside tolerance ({abs(now - timestamp)}s > {tolerance}s)")


def sign_standard(secret: str, msg_id: str, timestamp: int, body: bytes) -> str:
    signed = f"{msg_id}.{timestamp}.".encode() + body
    return "v1," + base64.b64encode(_hmac(standard_key(secret), signed)).decode()


def verify_standard(
    secret: str,
    msg_id: str,
    timestamp: int,
    body: bytes,
    signature_header: str,
    tolerance: int = DEFAULT_TOLERANCE,
    now: int | None = None,
) -> None:
    check_timestamp(timestamp, tolerance, now)
    expected = sign_standard(secret, msg_id, timestamp, body).split(",", 1)[1]
    for candidate in signature_header.split():
        version, _, value = candidate.partition(",")
        if version == "v1" and hmac.compare_digest(value.encode(), expected.encode()):
            return
    raise VerificationError("no matching v1 signature")


def sign_github(secret: str, body: bytes) -> str:
    return "sha256=" + _hmac(secret.encode(), body).hex()


def verify_github(secret: str, body: bytes, signature_header: str) -> None:
    if not hmac.compare_digest(sign_github(secret, body).encode(), signature_header.strip().encode()):
        raise VerificationError("X-Hub-Signature-256 does not match")


def sign_stripe(secret: str, timestamp: int, body: bytes) -> str:
    digest = _hmac(secret.encode(), f"{timestamp}.".encode() + body).hex()
    return f"t={timestamp},v1={digest}"


def parse_stripe_header(header: str) -> tuple[int, list[str]]:
    timestamp = None
    signatures = []
    for part in header.split(","):
        key, _, value = part.strip().partition("=")
        if key == "t":
            try:
                timestamp = int(value)
            except ValueError as exc:
                raise VerificationError("invalid t= timestamp") from exc
        elif key == "v1":
            signatures.append(value)
    if timestamp is None or not signatures:
        raise VerificationError("Stripe-Signature needs t= and at least one v1=")
    return timestamp, signatures


def verify_stripe(
    secret: str, body: bytes, signature_header: str, tolerance: int = DEFAULT_TOLERANCE, now: int | None = None
) -> None:
    timestamp, signatures = parse_stripe_header(signature_header)
    check_timestamp(timestamp, tolerance, now)
    expected = sign_stripe(secret, timestamp, body).split("v1=", 1)[1]
    if not any(hmac.compare_digest(expected.encode(), s.encode()) for s in signatures):
        raise VerificationError("no matching v1 signature")


def sign_hmac(secret: str, body: bytes, timestamp: int | None = None) -> str:
    message = (f"{timestamp}.".encode() + body) if timestamp is not None else body
    return _hmac(secret.encode(), message).hex()


def verify_hmac(
    secret: str,
    body: bytes,
    signature: str,
    timestamp: int | None = None,
    tolerance: int = DEFAULT_TOLERANCE,
    now: int | None = None,
) -> None:
    if timestamp is not None:
        check_timestamp(timestamp, tolerance, now)
    value = signature.strip()
    if value.startswith("sha256="):
        value = value[len("sha256=") :]
    if not hmac.compare_digest(sign_hmac(secret, body, timestamp).encode(), value.lower().encode()):
        raise VerificationError("signature does not match")


def read_secret(args) -> str:
    if args.secret_file:
        secret = Path(args.secret_file).read_text(encoding="utf-8").strip()
    else:
        secret = os.environ.get(args.secret_env, "")
    if not secret:
        source = args.secret_file or f"${args.secret_env}"
        raise SystemExit(f"error: no secret found in {source}")
    return secret


def read_body(args) -> bytes:
    if args.body_file and args.body_file != "-":
        return Path(args.body_file).read_bytes()
    return sys.stdin.buffer.read()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Sign or verify webhook payloads. The secret comes from an env var or file, never argv.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  export WEBHOOK_SECRET=...   # load from your secret store\n"
            "  python webhook_signature.py sign --scheme standard --id msg_1 --body-file event.json\n"
            "  python webhook_signature.py verify --scheme github --signature 'sha256=...' --body-file body.bin\n"
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("sign", "verify"):
        p = sub.add_parser(name, help=f"{name} a payload")
        p.add_argument("--scheme", choices=("standard", "github", "stripe", "hmac"), required=True)
        p.add_argument("--body-file", help="Raw request body file (default: stdin)")
        p.add_argument("--secret-env", default="WEBHOOK_SECRET", help="Env var holding the secret")
        p.add_argument("--secret-file", help="File holding the secret (overrides --secret-env)")
        p.add_argument("--id", dest="msg_id", help="Message id (standard scheme)")
        p.add_argument("--timestamp", type=int, help="Unix timestamp (default: now when signing)")
        p.add_argument("--format", choices=("text", "json"), default="text")
        if name == "verify":
            p.add_argument("--signature", required=True, help="Signature header value as received")
            p.add_argument(
                "--tolerance",
                type=int,
                default=DEFAULT_TOLERANCE,
                help="Max clock skew in seconds; -1 disables the check (default: 300)",
            )
            p.add_argument("--now", type=int, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    secret = read_secret(args)
    body = read_body(args)

    if args.command == "sign":
        ts = args.timestamp if args.timestamp is not None else int(time.time())
        try:
            if args.scheme == "standard":
                if not args.msg_id:
                    parser.error("--id is required for the standard scheme")
                headers = {
                    "webhook-id": args.msg_id,
                    "webhook-timestamp": str(ts),
                    "webhook-signature": sign_standard(secret, args.msg_id, ts, body),
                }
            elif args.scheme == "github":
                headers = {"X-Hub-Signature-256": sign_github(secret, body)}
            elif args.scheme == "stripe":
                headers = {"Stripe-Signature": sign_stripe(secret, ts, body)}
            else:
                use_ts = args.timestamp
                headers = {"X-Signature": sign_hmac(secret, body, use_ts)}
                if use_ts is not None:
                    headers["X-Timestamp"] = str(use_ts)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        if args.format == "json":
            print(json.dumps({"scheme": args.scheme, "headers": headers}, indent=2))
        else:
            for key, value in headers.items():
                print(f"{key}: {value}")
        return 0

    try:
        if args.scheme == "standard":
            if not args.msg_id or args.timestamp is None:
                parser.error("--id and --timestamp are required for the standard scheme")
            verify_standard(secret, args.msg_id, args.timestamp, body, args.signature, args.tolerance, args.now)
        elif args.scheme == "github":
            verify_github(secret, body, args.signature)
        elif args.scheme == "stripe":
            verify_stripe(secret, body, args.signature, args.tolerance, args.now)
        else:
            verify_hmac(secret, body, args.signature, args.timestamp, args.tolerance, args.now)
    except (VerificationError, ValueError) as exc:
        result = {"valid": False, "scheme": args.scheme, "reason": str(exc)}
        print(json.dumps(result) if args.format == "json" else f"INVALID: {exc}")
        return 1
    result = {"valid": True, "scheme": args.scheme}
    print(json.dumps(result) if args.format == "json" else "VALID")
    return 0


if __name__ == "__main__":
    sys.exit(main())
