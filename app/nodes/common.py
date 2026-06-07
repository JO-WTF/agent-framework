import datetime
import json
import re

from langchain_core.messages import AIMessage
from langchain_core.runnables.config import RunnableConfig

from app.config import PROMPTS
from app.memory.store import load_agent_notes, load_static_guidelines


def get_system_prompt(prompt_key: str) -> str:
    current_date_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    static_guidelines = load_static_guidelines()
    agent_notes = load_agent_notes()
    global_prompt = PROMPTS.get("global_context", "").replace("{current_date}", current_date_str)
    specific_prompt = PROMPTS.get(prompt_key, "").replace("{current_date}", current_date_str)

    sections = []
    if static_guidelines:
        sections.append("【静态全局规则】\n" + static_guidelines)
    if agent_notes:
        sections.append(agent_notes)
    sections.append(global_prompt)
    sections.append(specific_prompt)
    return "\n\n".join(sections).strip()


def silent_config(config: RunnableConfig) -> RunnableConfig:
    silent = dict(config or {})
    silent["callbacks"] = []
    return silent


def parse_json_object(raw_text: str) -> dict:
    text = raw_text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise


def format_todo_items(items: list[dict], indent: int = 0) -> list[str]:
    lines = []
    for item in items:
        status = item.get("status", "pending")
        item_id = item.get("id", "-")
        title = item.get("title", "")
        note = item.get("note", "")
        prefix = "  " * indent
        line = f"{prefix}- [{status}] {item_id} {title}".strip()
        if note:
            line = f"{line} ({note})"
        lines.append(line)
        children = item.get("children") or []
        if children:
            lines.extend(format_todo_items(children, indent + 1))
    return lines


def format_todo_context(state: dict) -> str:
    todo_list = state.get("todo_list") or []
    complexity = state.get("task_complexity", "simple")
    if not todo_list:
        return f"任务复杂度：{complexity}\n当前没有 todo list。"

    lines = format_todo_items(todo_list)
    return f"任务复杂度：{complexity}\n当前 todo list：\n" + "\n".join(lines)


def summarize_recent_messages(state: dict, limit: int = 8) -> str:
    summaries = []
    for message in state["messages"][-limit:]:
        role = message.__class__.__name__
        content = getattr(message, "content", "")
        tool_calls = getattr(message, "tool_calls", None)
        if tool_calls:
            content = f"{content}\n工具调用: {tool_calls}"
        summaries.append(f"{role}: {content}")
    return "\n\n".join(summaries)


def default_orchestrator_next(state: dict) -> str:
    last_message = state["messages"][-1]
    if isinstance(last_message, AIMessage) and not getattr(last_message, "tool_calls", None):
        return "evaluate"
    return "agent"
