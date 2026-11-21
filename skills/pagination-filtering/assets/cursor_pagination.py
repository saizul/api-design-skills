"""Reference implementation of opaque, tamper-evident keyset cursors and RFC 8288 Link headers.

Stdlib only. Copy into a project and adapt the query function to your ORM.

A cursor encodes the sort key of the last row on the page, for example
(created_at, id). The next page is ``WHERE (created_at, id) < (:created_at, :id)
ORDER BY created_at DESC, id DESC LIMIT :limit + 1``. Fetching one extra row
tells you whether another page exists without a COUNT(*).

Cursors are base64url JSON plus an HMAC so clients cannot forge or edit them;
they are opaque to clients, but not encrypted, so do not put secrets in them.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

CURSOR_VERSION = 1


class InvalidCursor(ValueError):
    """The cursor is malformed, tampered with or from another sort order. Return 400."""


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def encode_cursor(position: dict, secret: bytes, sort: str = "") -> str:
    payload = json.dumps({"v": CURSOR_VERSION, "s": sort, "p": position}, separators=(",", ":"), sort_keys=True)
    body = _b64(payload.encode())
    mac = _b64(hmac.new(secret, body.encode(), hashlib.sha256).digest()[:16])
    return f"{body}.{mac}"


def decode_cursor(cursor: str, secret: bytes, sort: str = "") -> dict:
    try:
        body, mac = cursor.split(".", 1)
        expected = _b64(hmac.new(secret, body.encode(), hashlib.sha256).digest()[:16])
        if not hmac.compare_digest(mac, expected):
            raise InvalidCursor("cursor signature mismatch")
        data = json.loads(_unb64(body))
    except InvalidCursor:
        raise
    except (ValueError, UnicodeDecodeError) as exc:
        raise InvalidCursor("malformed cursor") from exc
    if data.get("v") != CURSOR_VERSION:
        raise InvalidCursor("unsupported cursor version")
    if data.get("s") != sort:
        raise InvalidCursor("cursor was issued for a different sort order")
    return data["p"]


def clamp_limit(raw, default: int = 20, maximum: int = 100) -> int:
    """Parse a client-supplied page size; reject junk, cap at maximum."""
    if raw in (None, ""):
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("limit must be an integer") from exc
    if value < 1:
        raise ValueError("limit must be at least 1")
    return min(value, maximum)


def paginate(rows: list[dict], limit: int, key_fields: tuple[str, ...], secret: bytes, sort: str = "") -> dict:
    """Build a page from rows fetched with LIMIT limit + 1."""
    has_more = len(rows) > limit
    page = rows[:limit]
    next_cursor = None
    if has_more and page:
        last = page[-1]
        next_cursor = encode_cursor({k: last[k] for k in key_fields}, secret, sort)
    return {"data": page, "next_cursor": next_cursor, "has_more": has_more}


def link_header(request_url: str, next_cursor: str | None, prev_cursor: str | None = None) -> str | None:
    """RFC 8288 Link header with rel="next" / rel="prev", preserving other query parameters."""
    parts = urlsplit(request_url)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k != "cursor"]
    links = []
    for rel, cursor in (("next", next_cursor), ("prev", prev_cursor)):
        if cursor:
            url = urlunsplit(parts._replace(query=urlencode(query + [("cursor", cursor)])))
            links.append(f'<{url}>; rel="{rel}"')
    return ", ".join(links) or None


def parse_link_header(value: str) -> dict:
    """Parse a Link header into {rel: url}. Handles the common single-rel form."""
    result = {}
    for part in value.split(","):
        section = part.strip().split(";")
        if not section or not section[0].strip().startswith("<"):
            continue
        url = section[0].strip()[1:-1]
        for param in section[1:]:
            name, _, val = param.strip().partition("=")
            if name.lower() == "rel":
                for rel in val.strip('"').split():
                    result[rel] = url
    return result
