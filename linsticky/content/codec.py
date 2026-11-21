"""
Note content (de)serialization.

A note body is stored in the ``notes.content`` column as a list of segments::

    [{"text": "Hello ", "tags": []}, {"text": "world", "tags": ["bold"]}]

encoded as JSON and then hex-encoded. Older versions stored plain text (with
``<br>`` for new lines) or un-encoded JSON; both are still accepted on read.

This module is pure Python so it can be unit-tested without GTK.
"""
import json

EMPTY_SEGMENTS = [{"text": "", "tags": []}]


def _is_segment_list(value) -> bool:
    return isinstance(value, list) and all(isinstance(item, dict) for item in value)


def _normalize(segments: list) -> list[dict]:
    result = []
    for seg in segments:
        text = seg.get("text", "")
        tags = seg.get("tags", [])
        result.append({
            "text": text if isinstance(text, str) else str(text),
            "tags": [t for t in tags if isinstance(t, str)] if isinstance(tags, list) else [],
        })
    return result


def decode(raw) -> list[dict]:
    """
    Converts a stored ``content`` value into a list of segments.

    Accepted formats, in order: hex-encoded JSON (current), plain JSON,
    legacy plain text.
    """
    if not raw:
        return [dict(s) for s in EMPTY_SEGMENTS]
    if not isinstance(raw, str):
        raw = str(raw)

    try:
        value = json.loads(bytes.fromhex(raw).decode("utf-8"))
        if _is_segment_list(value):
            return _normalize(value)
    except (ValueError, TypeError):
        pass

    try:
        value = json.loads(raw)
        if _is_segment_list(value):
            return _normalize(value)
    except (ValueError, TypeError):
        pass

    return [{"text": raw.replace("<br>", "\n"), "tags": []}]


def encode(segments: list[dict]) -> str:
    """Serializes segments into the storage format (hex-encoded JSON)."""
    return json.dumps(segments).encode("utf-8").hex()


def plain_text(segments: list[dict]) -> str:
    """Concatenated text of all segments, without formatting."""
    return "".join(seg.get("text", "") for seg in segments)
