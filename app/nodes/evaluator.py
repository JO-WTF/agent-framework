from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables.config import RunnableConfig

from app.config import AgentState, llm_client
from app.logging_config import logger
from app.memory.store import trim_messages
from app.nodes.common import format_todo_context, get_system_prompt, silent_config, summarize_recent_messages


async def evaluate_response_node(state: AgentState, config: RunnableConfig):
    logger.info("🕵️ \033[93m[Node: Evaluator]\033[0m 质检员正在审查答复...")
    rev_count = state.get("revision_count", 0)

    if rev_count >= 3:
        logger.warning("⚠️ \033[91m[熔断]\033[0m 达最大重试，强制通过。")
        return {"eval_status": "PASS"}

    user_q = next((m.content for m in reversed(state["messages"][:-1]) if isinstance(m, HumanMessage)), "")
    draft_reply = state["messages"][-1].content
    session_id = state.get("session_id")
    trimmed_messages = trim_messages(state["messages"], session_id=session_id)
    recent_messages = summarize_recent_messages({"messages": trimmed_messages})

    system_prompt = get_system_prompt("evaluator")
    response = await llm_client.ainvoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=(
            f"问题: {user_q}\n\n"
            f"Orchestrator todo 状态:\n{format_todo_context(state)}\n\n"
            f"最近上下文摘要:\n{recent_messages}\n\n"
            f"回复:\n{draft_reply}"
        ))
    ], silent_config(config))
    eval_result = response.content.strip()

    if eval_result.startswith("REJECT"):
        reason = eval_result.replace("REJECT:", "").strip()
        logger.warning(f"❌ \033[35m[不合格]\033[0m 打回重做。原因: {reason}")
        reject_msg = HumanMessage(content=f"[质检打回] 回答不合格！原因：{reason}。请参考 todo list 重新规划下一步，并重新调用必要工具获取数据。")
        return {"eval_status": "REJECT", "revision_count": rev_count + 1, "messages": [reject_msg]}

    logger.info("✅ \033[92m[合格]\033[0m 准备输出。")
    return {"eval_status": "PASS"}
