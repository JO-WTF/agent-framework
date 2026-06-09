"""Utilities for extracting streamed LLM thinking and content chunks."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

THINKING_KEYS = (
    "reasoning",
    "reasoning_content",
    "thinking",
    "reasoning_delta",
)
THINKING_BLOCK_TYPES = (
    "thinking",
    "reasoning",
    "reasoning_content",
    "reasoning_delta",
)
TEXT_BLOCK_TYPES = ("text", "output_text")


def _get_attr_or_key(obj: Any, key: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, Mapping):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _first_text_value(obj: Any, keys: tuple[str, ...]) -> str:
    for key in keys:
        value = _get_attr_or_key(obj, key)
        if value:
            return str(value)
    return ""


def _normalize_content(content: Any) -> str:
    """Normalize LangChain chunk content into plain streamed text."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts: list[str] = []
        for block in content:
            if isinstance(block, str):
                texts.append(block)
                continue

            block_type = _get_attr_or_key(block, "type")
            if block_type in THINKING_BLOCK_TYPES:
                continue
            if block_type in TEXT_BLOCK_TYPES:
                texts.append(_first_text_value(block, ("text", "content")))
                continue

            texts.append(_first_text_value(block, ("text", "content")))
        return "".join(texts)
    return str(content)


def _extract_from_mapping_or_object(obj: Any) -> str:
    return _first_text_value(obj, THINKING_KEYS)


def _first_delta_from_chunk(chunk: Any) -> Any:
    choices = _get_attr_or_key(chunk, "choices")
    if not choices:
        nested_chunk = _get_attr_or_key(chunk, "chunk")
        choices = _get_attr_or_key(nested_chunk, "choices")
    if not choices:
        return None

    first_choice = choices[0]
    return _get_attr_or_key(first_choice, "delta")


def _extract_thinking_from_content_blocks(content: Any) -> str:
    if not isinstance(content, list):
        return ""

    thoughts: list[str] = []
    for block in content:
        block_type = _get_attr_or_key(block, "type")
        if block_type not in THINKING_BLOCK_TYPES:
            continue
        thoughts.append(
            _first_text_value(
                block,
                (
                    "thinking",
                    "reasoning",
                    "reasoning_content",
                    "reasoning_delta",
                    "text",
                    "content",
                ),
            )
        )
    return "".join(thoughts)


def extract_thinking_and_content(chunk: Any) -> tuple[str, str]:
    """Extract provider thinking/reasoning text and answer content from a stream chunk.

    LangChain callbacks usually pass a ``ChatGenerationChunk`` in ``kwargs["chunk"]``;
    direct ``astream`` usage often yields an ``AIMessageChunk``. This helper accepts
    both shapes and checks common provider-specific locations that may survive the
    LangChain conversion layer.
    """
    if chunk is None:
        return "", ""

    message_chunk = getattr(chunk, "message", chunk)
    delta = _first_delta_from_chunk(chunk)
    raw_content = getattr(message_chunk, "content", None)
    if raw_content is None and delta is not None:
        raw_content = _get_attr_or_key(delta, "content")

    delta_additional_kwargs = _get_attr_or_key(delta, "additional_kwargs", {}) or {}
    additional_kwargs = getattr(message_chunk, "additional_kwargs", {}) or {}
    response_metadata = getattr(message_chunk, "response_metadata", {}) or {}

    thinking = (
        _extract_from_mapping_or_object(delta)
        or _extract_from_mapping_or_object(delta_additional_kwargs)
        or _extract_from_mapping_or_object(message_chunk)
        or _extract_from_mapping_or_object(additional_kwargs)
        or _extract_from_mapping_or_object(response_metadata)
        or _extract_thinking_from_content_blocks(raw_content)
    )

    content = _normalize_content(raw_content)
    if not content:
        content = getattr(chunk, "text", "") or ""

    return thinking, content
