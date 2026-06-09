"""Console logging helpers for LLM prompts, thinking, and responses."""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from app.llm_streaming import extract_thinking_and_content
from app.logging_config import logger

_THINK_RE = re.compile(r"<think>(.*?)</think>", re.DOTALL)
_GREY = "\033[90m"
_RESET = "\033[0m"


def _grey(text: str) -> str:
    return f"{_GREY}{text}{_RESET}" if text else text


def _message_role(message: Any) -> str:
    if isinstance(message, SystemMessage):
        return "system"
    if isinstance(message, HumanMessage):
        return "user"
    if isinstance(message, AIMessage):
        return "assistant"
    if isinstance(message, ToolMessage):
        return "tool"
    return getattr(message, "type", message.__class__.__name__)


def _stringify_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        _, normalized = extract_thinking_and_content(type("Chunk", (), {"content": content})())
        return normalized or json.dumps(content, ensure_ascii=False, default=str)
    return str(content)


def _extract_thinking_from_response(response: Any) -> tuple[str, str]:
    thinking_parts: list[str] = []
    additional_kwargs = getattr(response, "additional_kwargs", {}) or {}
    for key in ("reasoning_content", "thinking", "reasoning", "reasoning_delta"):
        value = additional_kwargs.get(key)
        if value:
            thinking_parts.append(str(value))

    raw_content = getattr(response, "content", response)
    content = _stringify_content(raw_content)
    match = _THINK_RE.search(content)
    if match:
        thinking_parts.append(match.group(1).strip())
        content = _THINK_RE.sub("", content).strip()

    return "".join(thinking_parts).strip(), content


def _format_non_user_messages(messages: list[Any]) -> str:
    lines: list[str] = []
    for index, message in enumerate(messages, start=1):
        if isinstance(message, HumanMessage):
            continue
        role = _message_role(message)
        content = _stringify_content(getattr(message, "content", message))
        lines.append(f"[{index}] {role}:\n{content}")
    return "\n\n".join(lines).strip() or "(none)"


def _format_user_prompts(messages: list[Any]) -> str:
    prompts = [
        _stringify_content(getattr(message, "content", ""))
        for message in messages
        if isinstance(message, HumanMessage)
    ]
    return "\n\n---\n\n".join(prompt for prompt in prompts if prompt).strip() or "(no user prompt)"


def log_user_question(source: str, question: str) -> None:
    logger.info("\n%s\n👤 [User Question: %s]\n%s\n%s", "=" * 80, source, question, "=" * 80)


def log_llm_request(node_name: str, messages: list[Any]) -> None:
    logger.info(
        "\n%s\n📤 [LLM Request: %s]\n【User Prompt】\n%s\n\n【System/Context Messages】\n%s\n%s",
        "=" * 80,
        node_name,
        _grey(_format_user_prompts(messages)),
        _grey(_format_non_user_messages(messages)),
        "=" * 80,
    )


def log_llm_response(node_name: str, response: Any) -> None:
    thinking, content = _extract_thinking_from_response(response)
    tool_calls = getattr(response, "tool_calls", None) or []
    tool_call_text = ""
    if tool_calls:
        tool_call_text = "\n\n【Tool Calls】\n" + json.dumps(tool_calls, ensure_ascii=False, default=str, indent=2)

    logger.info(
        "\n%s\n📥 [LLM Response: %s]\n【Thinking】\n%s\n\n【Model Reply】\n%s%s\n%s",
        "=" * 80,
        node_name,
        thinking or "(empty)",
        content or "(empty)",
        tool_call_text,
        "=" * 80,
    )
