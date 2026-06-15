import asyncio
from typing import Any

from langchain_core.messages import ToolMessage
from langchain_core.runnables.config import RunnableConfig

from app.config import AgentState
from app.nodes.tool_execution_subgraph import get_max_retries, tool_execution_subgraph
from app.tools.context import set_session_id
from app.memory.store import store_tool_result, summarize_text


SAFE_PARALLEL_TOOLS = {
    "search_web",
    "fetch_url",
    "read_webpage",
    "api_request",
    "list_tool_results",
    "read_tool_result",
    "list_skills",
    "get_skill_sop",
    "sandbox_status",
    "geocode_address",
    "reverse_geocode",
}

EXEMPT_TOOLS = {"read_tool_result", "list_tool_results", "read_file", "view_file"}


async def _execute_tool_call(tool_call: dict[str, Any], session_id: str, config: RunnableConfig) -> str:
    sub_graph_result = await tool_execution_subgraph.ainvoke(
        {
            "original_request": tool_call,
            "tool_call_id": tool_call["id"],
            "tool_name": tool_call["name"],
            "args": tool_call.get("args", {}),
            "session_id": session_id,
            "retry_count": 0,
            "max_retries": get_max_retries(tool_call["name"]),
            "internal_messages": [],
            "status": "pending",
            "final_result": "",
        },
        config=config,
    )
    return sub_graph_result["final_result"]


def _format_tool_message_content(tool_name: str, raw_output: str, session_id: str) -> str:
    if tool_name in EXEMPT_TOOLS:
        return raw_output
    if raw_output.startswith("结果内容过长，已保存为引用"):
        return raw_output
    if len(raw_output) <= 800:
        return raw_output

    ref_id = store_tool_result(tool_name, raw_output, session_id=session_id)
    summary = summarize_text(raw_output, max_chars=256)
    return f"已保存为引用 {ref_id}\n摘要: {summary}"


async def tools_execution_node(state: AgentState, config: RunnableConfig):
    session_id = state.get("session_id", "cli")
    set_session_id(session_id)

    last_message = state["messages"][-1]
    tool_calls = getattr(last_message, "tool_calls", None) or []
    tool_messages: list[ToolMessage | None] = [None] * len(tool_calls)
    parallel_tasks: list[tuple[int, dict[str, Any], asyncio.Task[str]]] = []

    for index, tool_call in enumerate(tool_calls):
        tool_name = tool_call["name"]
        if tool_name in SAFE_PARALLEL_TOOLS:
            parallel_tasks.append((index, tool_call, asyncio.create_task(_execute_tool_call(tool_call, session_id, config))))
        else:
            raw_output = await _execute_tool_call(tool_call, session_id, config)
            tool_messages[index] = ToolMessage(
                content=_format_tool_message_content(tool_name, raw_output, session_id),
                tool_call_id=tool_call["id"],
            )

    for index, tool_call, task in parallel_tasks:
        raw_output = await task
        tool_messages[index] = ToolMessage(
            content=_format_tool_message_content(tool_call["name"], raw_output, session_id),
            tool_call_id=tool_call["id"],
        )

    return {"messages": [message for message in tool_messages if message is not None], "last_node": "tools"}
