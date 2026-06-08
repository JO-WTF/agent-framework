from langchain_core.messages import ToolMessage
from langchain_core.runnables.config import RunnableConfig

from app.config import AgentState
from app.nodes.tool_execution_subgraph import get_max_retries, tool_execution_subgraph
from app.tools.context import set_session_id


async def tools_execution_node(state: AgentState, config: RunnableConfig):
    session_id = state.get("session_id", "cli")
    set_session_id(session_id)

    last_message = state["messages"][-1]
    tool_calls = getattr(last_message, "tool_calls", None) or []
    tool_messages: list[ToolMessage] = []

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
        tool_messages.append(
            ToolMessage(
                content=sub_graph_result["final_result"],
                tool_call_id=tool_call["id"],
            )
        )

    return {"messages": tool_messages}
