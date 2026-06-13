from langchain_core.messages import ToolMessage
from langchain_core.runnables.config import RunnableConfig

from app.config import AgentState
from app.nodes.tool_execution_subgraph import get_max_retries, tool_execution_subgraph
from app.tools.context import set_session_id
from app.memory.store import store_tool_result, summarize_text


async def tools_execution_node(state: AgentState, config: RunnableConfig):
    session_id = state.get("session_id", "cli")
    set_session_id(session_id)

    last_message = state["messages"][-1]
    tool_calls = getattr(last_message, "tool_calls", None) or []
    tool_messages: list[ToolMessage] = []

    EXEMPT_TOOLS = {"read_tool_result", "list_tool_results", "read_file", "view_file"}

    for tool_call in tool_calls:
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
        raw_output = sub_graph_result["final_result"]
        tool_name = tool_call["name"]
        
        if tool_name in EXEMPT_TOOLS:
            content = raw_output
        elif raw_output.startswith("结果内容过长，已保存为引用"):
            content = raw_output
        elif len(raw_output) <= 800:
            content = raw_output
        else:
            ref_id = store_tool_result(tool_name, raw_output, session_id=session_id)
            summary = summarize_text(raw_output, max_chars=256)
            content = f"已保存为引用 {ref_id}\n摘要: {summary}"

        tool_messages.append(
            ToolMessage(
                content=content,
                tool_call_id=tool_call["id"],
            )
        )

    return {"messages": tool_messages, "last_node": "tools"}
