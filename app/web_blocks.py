"""Server-side parsing of assistant replies into renderable blocks.

The web console renders assistant messages as an ordered list of *blocks* so a
single reply can interleave markdown text with rich widgets (maps, weather
cards, image carousels, ...). The contract is server-driven: the backend
normalizes whatever the LLM produced into a clean ``blocks`` array and the
frontend only has to know how to render each block type.

Widgets are embedded by the model with a fenced code block tagged ``widget``
whose body is a JSON object, e.g.::

    ```widget
    {"widget_type": "map", "id": "w1", "props": {"center": {"lat": 1, "lng": 2}}}
    ```

Everything outside such fences becomes ``text`` blocks (markdown).
"""

import json
import re
from typing import Any

# Matches a fenced code block tagged ``widget`` (3+ backticks or tildes).
_WIDGET_FENCE_RE = re.compile(
    r"^[ \t]*(?P<fence>`{3,}|~{3,})[ \t]*widget[ \t]*\r?\n"
    r"(?P<body>.*?)\r?\n?"
    r"^[ \t]*(?P=fence)[ \t]*$",
    re.DOTALL | re.MULTILINE,
)


def _text_block(content: str) -> dict[str, Any]:
    return {"type": "text", "format": "markdown", "content": content}


def _widget_block(payload: dict[str, Any]) -> dict[str, Any] | None:
    widget_type = payload.get("widget_type")
    if not isinstance(widget_type, str) or not widget_type.strip():
        return None
    block: dict[str, Any] = {
        "type": "widget",
        "widget_type": widget_type.strip(),
        "props": payload.get("props") if isinstance(payload.get("props"), dict) else {},
    }
    widget_id = payload.get("id")
    if isinstance(widget_id, str) and widget_id.strip():
        block["id"] = widget_id.strip()
    return block


def parse_message_blocks(content: str) -> list[dict[str, Any]]:
    """Split assistant ``content`` into an ordered list of text/widget blocks.

    Text segments keep their original markdown (including any ``<think>`` tags so
    the frontend can still surface reasoning). Widget fences whose body is not a
    valid JSON object are left untouched as text so nothing is silently dropped.
    """
    text = content or ""
    blocks: list[dict[str, Any]] = []
    cursor = 0

    for match in _WIDGET_FENCE_RE.finditer(text):
        widget_block: dict[str, Any] | None = None
        try:
            payload = json.loads(match.group("body"))
        except (json.JSONDecodeError, ValueError):
            payload = None
        if isinstance(payload, dict):
            widget_block = _widget_block(payload)

        if widget_block is None:
            # Not a valid widget; keep the raw fence as text.
            continue

        leading = text[cursor : match.start()]
        if leading.strip():
            blocks.append(_text_block(leading.strip()))
        blocks.append(widget_block)
        cursor = match.end()

    trailing = text[cursor:]
    if trailing.strip():
        blocks.append(_text_block(trailing.strip()))

    if not blocks and text.strip():
        blocks.append(_text_block(text.strip()))

    return blocks


def message_has_widgets(blocks: list[dict[str, Any]]) -> bool:
    return any(block.get("type") == "widget" for block in blocks)
