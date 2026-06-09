"""DeepSeek-specific ChatOpenAI compatibility helpers."""

from __future__ import annotations

from typing import Any

from langchain_openai import ChatOpenAI

_REASONING_KEYS = ("reasoning_content", "reasoning", "thinking", "reasoning_delta")


class ChatDeepSeekReasoning(ChatOpenAI):
    """ChatOpenAI variant that preserves DeepSeek reasoning deltas.

    DeepSeek's OpenAI-compatible streaming API emits reasoning tokens in
    ``choices[0].delta.reasoning_content``. The stock ``ChatOpenAI`` converter
    currently only maps ``delta.content`` into the LangChain chunk, so callbacks
    receive empty ``token`` values during reasoning. This subclass keeps those
    fields in ``AIMessageChunk.additional_kwargs`` so existing stream extractors
    can display them.
    """

    def _convert_chunk_to_generation_chunk(self, chunk: dict, default_chunk_class: type, base_generation_info: dict | None):
        generation_chunk = super()._convert_chunk_to_generation_chunk(chunk, default_chunk_class, base_generation_info)
        if generation_chunk is None:
            return None

        delta = _first_delta(chunk)
        if delta:
            additional_kwargs = getattr(generation_chunk.message, "additional_kwargs", None)
            if isinstance(additional_kwargs, dict):
                for key in _REASONING_KEYS:
                    value = delta.get(key)
                    if value:
                        additional_kwargs[key] = value
                        # Normalize the most common downstream key while keeping
                        # provider-specific aliases available for debugging.
                        additional_kwargs.setdefault("reasoning_content", value)
        return generation_chunk


def _first_delta(chunk: dict[str, Any]) -> dict[str, Any]:
    choices = chunk.get("choices", []) or chunk.get("chunk", {}).get("choices", [])
    if not choices:
        return {}
    delta = choices[0].get("delta") or {}
    return delta if isinstance(delta, dict) else {}
