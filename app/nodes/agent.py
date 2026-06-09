from langchain_core.messages import SystemMessage
from langchain_core.runnables.config import RunnableConfig

from app.config import AgentState, get_llm_client_from_config
from app.logging_config import logger
from app.llm_logging import log_llm_request, log_llm_response
from app.memory.store import trim_messages
from app.nodes.common import format_todo_context, get_system_prompt
from app.tools.registry import AGENT_TOOLS


async def agent_reasoning_node(state: AgentState, config: RunnableConfig):
    logger.info("🧠 \033[92m[Node: Agent Brain]\033[0m 正在分析请求...")
    context_tags = state.get("context_tags")
    system_prompt = (
        f"{get_system_prompt('agent_brain', context_tags=context_tags)}\n\n"
        f"【Orchestrator 任务计划】\n{format_todo_context(state)}"
    )
    session_id = state.get("session_id")
    messages = [SystemMessage(content=system_prompt)] + trim_messages(state["messages"], session_id=session_id)
    log_llm_request("agent", messages)
    response = await get_llm_client_from_config(config).bind_tools(AGENT_TOOLS).ainvoke(messages, config)
    log_llm_response("agent", response)
    return {"messages": [response], "last_node": "agent"}
