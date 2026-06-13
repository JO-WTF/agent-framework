from langchain_core.messages import SystemMessage
from langchain_core.runnables.config import RunnableConfig

from app.config import AgentState, get_llm_client_from_config
from app.logging_config import logger
from app.llm_logging import log_llm_request, log_llm_response
from app.memory.store import trim_messages
from app.nodes.common import format_todo_context, get_system_prompt
from app.tools.registry import get_agent_tools


def _recent_text_for_tool_selection(messages: list, limit: int = 6) -> str:
    parts: list[str] = []
    for message in messages[-limit:]:
        parts.append(str(getattr(message, "content", "")))
        tool_calls = getattr(message, "tool_calls", None)
        if tool_calls:
            parts.append(str(tool_calls))
    return "\n".join(parts)


async def agent_reasoning_node(state: AgentState, config: RunnableConfig):
    logger.info("🧠 \033[92m[Node: Agent Brain]\033[0m 正在分析请求...")
    context_tags = state.get("context_tags")
    system_prompt = (
        f"{get_system_prompt('agent_brain', context_tags=context_tags)}\n\n"
        f"【Orchestrator 任务计划】\n{format_todo_context(state)}"
    )
    session_id = state.get("session_id")
    trimmed_history = trim_messages(state["messages"], session_id=session_id)
    messages = [SystemMessage(content=system_prompt)] + trimmed_history
    agent_tools = get_agent_tools(context_tags, recent_text=_recent_text_for_tool_selection(trimmed_history))
    log_llm_request("agent", messages)

    session = None
    if session_id:
        from app.web import manager
        session = manager.sessions.get(session_id)
        if session:
            await session.set_llm_active("agent")

    try:
        response = await get_llm_client_from_config(config).bind_tools(agent_tools).ainvoke(messages, config)
    finally:
        if session:
            await session.set_llm_active(None)

    log_llm_response("agent", response)
    return {"messages": [response], "last_node": "agent"}
