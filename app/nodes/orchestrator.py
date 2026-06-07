import json

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables.config import RunnableConfig

from app.config import AgentState, llm_client
from app.logging_config import logger
from app.memory.store import trim_messages
from app.nodes.common import (
    default_orchestrator_next,
    format_todo_items,
    get_system_prompt,
    parse_json_object,
    silent_config,
    summarize_recent_messages,
)


async def orchestrator_node(state: AgentState, config: RunnableConfig):
    logger.info("🧭 \033[94m[Node: Orchestrator]\033[0m 正在判断任务复杂度并更新 todo list...")
    system_prompt = get_system_prompt("orchestrator")
    current_todo_json = json.dumps(state.get("todo_list", []), ensure_ascii=False, indent=2)
    session_id = state.get("session_id")
    trimmed_messages = trim_messages(state["messages"], session_id=session_id)
    recent_messages = summarize_recent_messages({"messages": trimmed_messages})

    user_prompt = (
        f"当前任务复杂度: {state.get('task_complexity', 'unknown')}\n\n"
        f"当前 todo_list JSON:\n{current_todo_json}\n\n"
        f"最近消息:\n{recent_messages}"
    )

    response = await llm_client.ainvoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt)
    ], silent_config(config))

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
    except Exception as exc:
        logger.warning(f"⚠️ \033[93m[Orchestrator]\033[0m JSON 解析失败，使用保守路由。原因: {exc}")
        complexity = state.get("task_complexity", "simple")
        todo_list = state.get("todo_list", [])
        next_node = default_orchestrator_next(state)

    # Only a final AI reply can be evaluated. A fresh user message, tool result,
    # or AI tool-call must always go back to the agent first.
    default_next = default_orchestrator_next(state)
    next_node = "evaluate" if default_next == "evaluate" else "agent"

    if todo_list:
        logger.info("\n".join(["📋 \033[94m[Todo]\033[0m"] + format_todo_items(todo_list)))
    else:
        logger.info(f"📋 \033[94m[Todo]\033[0m 无，任务复杂度: {complexity}")

    return {
        "task_complexity": complexity,
        "todo_list": todo_list,
        "orchestrator_next": next_node,
        "orchestrator_think": think_content,
        "orchestrator_message": message_content,
        "orchestrator_prompt": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }


