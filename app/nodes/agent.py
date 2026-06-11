from langchain_core.messages import SystemMessage
from langchain_core.runnables.config import RunnableConfig

from app.config import AgentState, get_llm_client_from_config
from app.logging_config import logger
from app.llm_logging import log_llm_request, log_llm_response
from app.memory.store import trim_messages
from app.nodes.common import format_todo_context, get_system_prompt
from app.tools.registry import get_tools_for_agent_role


async def _run_agent_node(
    state: AgentState,
    config: RunnableConfig,
    *,
    prompt_key: str,
    node_name: str,
    log_label: str,
    context_tags: list[str] | str | None = None,
    agent_role: str = "general",
):
    logger.info(f"🧠 \033[92m[Node: {log_label}]\033[0m 正在分析请求...")
    selected_context_tags = context_tags if context_tags is not None else state.get("context_tags")
    system_prompt = (
        f"{get_system_prompt(prompt_key, context_tags=selected_context_tags)}\n\n"
        f"【Orchestrator 任务计划】\n{format_todo_context(state)}"
    )
    session_id = state.get("session_id")
    messages = [SystemMessage(content=system_prompt)] + trim_messages(state["messages"], session_id=session_id)
    log_llm_request(node_name, messages)

    session = None
    if session_id:
        from app.web import manager
        session = manager.sessions.get(session_id)
        if session:
            await session.set_llm_active(node_name)

    try:
        response = await (
            get_llm_client_from_config(config)
            .bind_tools(get_tools_for_agent_role(agent_role))
            .ainvoke(messages, config)
        )
    finally:
        if session:
            await session.set_llm_active(None)

    log_llm_response(node_name, response)
    return {"messages": [response], "last_node": node_name}


async def agent_reasoning_node(state: AgentState, config: RunnableConfig):
    return await _run_agent_node(
        state,
        config,
        prompt_key="agent_brain",
        node_name="agent",
        log_label="Agent Brain",
        agent_role="general",
    )


async def network_specialist_agent_node(state: AgentState, config: RunnableConfig):
    context_tags = ["network", *[tag for tag in state.get("context_tags", []) if tag != "network"]]
    return await _run_agent_node(
        state,
        config,
        prompt_key="network_specialist_agent",
        node_name="network_specialist_agent",
        log_label="Network Specialist Agent",
        context_tags=context_tags,
        agent_role="network",
    )
