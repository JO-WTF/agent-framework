import asyncio
from typing import Any

from langchain_core.messages import ToolMessage
from langchain_core.runnables.config import RunnableConfig

from app.config import AgentState
from app.nodes.tool_execution_subgraph import get_max_retries, tool_execution_subgraph
from app.tools.context import set_session_id


SAFE_PARALLEL_TOOLS = {
    "search_web",
    "list_tool_results",
    "read_tool_result",
    "list_skills",
    "get_skill_sop",
    "sandbox_status",
}


async def _execute_tool_call(tool_call: dict[str, Any], session_id: str, config: RunnableConfig) -> ToolMessage:
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
    return ToolMessage(
        content=sub_graph_result["final_result"],
        tool_call_id=tool_call["id"],
    )


async def tools_execution_node(state: AgentState, config: RunnableConfig):
    session_id = state.get("session_id", "cli")
    set_session_id(session_id)

    last_message = state["messages"][-1]
    tool_calls = getattr(last_message, "tool_calls", None) or []
    tool_messages: list[ToolMessage | None] = [None] * len(tool_calls)
    parallel_tasks: list[tuple[int, asyncio.Task[ToolMessage]]] = []

    for index, tool_call in enumerate(tool_calls):
        if tool_call["name"] in SAFE_PARALLEL_TOOLS:
            parallel_tasks.append((index, asyncio.create_task(_execute_tool_call(tool_call, session_id, config))))
        else:
            tool_messages[index] = await _execute_tool_call(tool_call, session_id, config)

    for index, task in parallel_tasks:
        tool_messages[index] = await task

    return {"messages": [message for message in tool_messages if message is not None], "last_node": "tools"}
