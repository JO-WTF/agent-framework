import json

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables.config import RunnableConfig

from app.agents.contracts import format_agent_contracts_for_orchestrator
from app.config import AgentState, llm_client
from app.logging_config import logger
from app.llm_logging import log_llm_request, log_llm_response
from app.memory.store import normalize_context_tags, trim_messages, get_active_skill_names
from app.nodes.common import (
    default_orchestrator_next,
    format_available_context_tags,
    format_todo_items,
    get_system_prompt,
    infer_context_tags_from_state,
    parse_json_object,
    silent_config,
    summarize_recent_messages,
)


def _is_final_agent_reply(state: AgentState) -> bool:
    messages = state.get("messages", [])
    if state.get("last_node") not in {"agent", "network_specialist_agent"} or not messages:
        return False
    last_message = messages[-1]
    return (
        isinstance(last_message, AIMessage)
        and not getattr(last_message, "tool_calls", None)
        and bool(str(getattr(last_message, "content", "")).strip())
    )


async def orchestrator_node(state: AgentState, config: RunnableConfig):
    logger.info("🧭 \033[94m[Node: Orchestrator]\033[0m 正在判断任务复杂度并更新 todo list...")
    if _is_final_agent_reply(state):
        context_tags = normalize_context_tags(state.get("context_tags"))[:4]
        return {
            "task_complexity": state.get("task_complexity", "simple"),
            "todo_list": state.get("todo_list", []),
            "orchestrator_next": "evaluate",
            "agent_role": state.get("agent_role", "general"),
            "context_tags": context_tags,
            "active_skills": get_active_skill_names(context_tags),
            "last_node": "orchestrator",
            "orchestrator_think": "",
            "orchestrator_message": "Fast-path: final agent reply is ready for evaluation.",
            "orchestrator_prompt": [],
        }

    initial_context_tags = infer_context_tags_from_state(state)[:4]
    system_prompt = get_system_prompt("orchestrator", context_tags=initial_context_tags)
    current_todo_json = json.dumps(state.get("todo_list", []), ensure_ascii=False, indent=2)
    session_id = state.get("session_id")
    trimmed_messages = trim_messages(state["messages"], session_id=session_id)
    recent_messages = summarize_recent_messages({"messages": trimmed_messages})

    user_prompt = (
        f"当前任务复杂度: {state.get('task_complexity', 'unknown')}\n\n"
        f"可选上下文标签: {format_available_context_tags()}\n\n"
        f"Agent 能力边界与计划约束:\n{format_agent_contracts_for_orchestrator()}\n\n"
        f"当前 todo_list JSON:\n{current_todo_json}\n\n"
        f"最近消息:\n{recent_messages}"
    )

    llm_messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]
    log_llm_request("orchestrator", llm_messages)
    
    session = None
    if session_id:
        from app.web import manager
        session = manager.sessions.get(session_id)
        if session:
            await session.set_llm_active("orchestrator")
            
    try:
        response = await llm_client.ainvoke(llm_messages, silent_config(config))
    finally:
        if session:
            await session.set_llm_active(None)

    log_llm_response("orchestrator", response)

    import re

    think_content = ""
    message_content = response.content or ""
    if hasattr(response, "additional_kwargs") and isinstance(response.additional_kwargs, dict):
        think_content = response.additional_kwargs.get("reasoning_content", "") or ""

    match = re.search(r"<think>(.*?)</think>", response.content, re.DOTALL) if response.content else None
    if match:
        if not think_content:
            think_content = match.group(1).strip()
        message_content = response.content.replace(match.group(0), "").strip()


    try:
        parsed = parse_json_object(message_content)
        complexity = parsed.get("task_complexity", state.get("task_complexity", "simple"))
        todo_list = parsed.get("todo_list", state.get("todo_list", []))
        next_node = parsed.get("next", default_orchestrator_next(state))
        if next_node not in {"agent", "evaluate"}:
            next_node = default_orchestrator_next(state)
        raw_context_tags = parsed.get("context_tags")
        if isinstance(raw_context_tags, (list, str)):
            context_tags = normalize_context_tags(raw_context_tags)
            for tag in initial_context_tags:
                if tag not in context_tags:
                    context_tags.append(tag)
            context_tags = context_tags[:4]
        else:
            context_tags = initial_context_tags[:4]
        
        agent_role = str(parsed.get("agent_role") or state.get("agent_role") or "general").strip().lower().replace("-", "_")
        if agent_role not in {"general", "network"}:
            agent_role = "general"
        if "network" in context_tags:
            agent_role = "network"
        if agent_role == "network" and "network" not in context_tags:
            context_tags = (["network"] + context_tags)[:4]
    except Exception as exc:
        logger.warning(f"⚠️ \033[93m[Orchestrator]\033[0m JSON 解析失败，使用保守路由。原因: {exc}")
        complexity = state.get("task_complexity", "simple")
        todo_list = state.get("todo_list", [])
        next_node = default_orchestrator_next(state)
        context_tags = initial_context_tags
        agent_role = state.get("agent_role", "general")
        if agent_role == "network" and "network" not in context_tags:
            context_tags = (["network"] + context_tags)[:4]

    # Only a final AI reply can be evaluated. A fresh user message, tool result,
    # or AI tool-call must always go back to the agent first.
    default_next = default_orchestrator_next(state)
    next_node = "evaluate" if default_next == "evaluate" else "agent"
    if next_node == "evaluate":
        agent_role = state.get("agent_role", agent_role)

    if todo_list:
        logger.info("\n".join(["📋 \033[94m[Todo]\033[0m"] + format_todo_items(todo_list)))
    else:
        logger.info(f"📋 \033[94m[Todo]\033[0m 无，任务复杂度: {complexity}")

    return {
        "task_complexity": complexity,
        "todo_list": todo_list,
        "orchestrator_next": next_node,
        "agent_role": agent_role,
        "context_tags": context_tags,
        "active_skills": get_active_skill_names(context_tags),
        "last_node": "orchestrator",
        "orchestrator_think": think_content,
        "orchestrator_message": message_content,
        "orchestrator_prompt": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
