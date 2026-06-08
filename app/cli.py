import sys
import uuid
import asyncio
from langchain_core.messages import HumanMessage
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from app.config import AgentState, StreamingConsoleCallback
from app.memory.store import trim_messages
from app.nodes import (
    agent_reasoning_node,
    evaluate_response_node,
    memory_manager_node,
    orchestrator_node,
    route_after_memory,
    tools_execution_node,
)
from app.logging_config import logger

# ----------------- 路由裁判逻辑 -----------------
def route_after_evaluation(state: AgentState) -> str:
    """质检完去哪儿？通过就结束，不通过就回大脑"""
    if state["eval_status"] == "PASS":
        return "end"
    return "orchestrator"

# ----------------- 图的组装 -----------------
def build_agent_graph():
    workflow = StateGraph(AgentState)
    workflow.add_node("orchestrator", orchestrator_node)
    workflow.add_node("agent", agent_reasoning_node)
    workflow.add_node("tools", tools_execution_node)
    workflow.add_node("memory", memory_manager_node)
    workflow.add_node("evaluate", evaluate_response_node)

    workflow.add_edge(START, "orchestrator")
    workflow.add_edge("orchestrator", "memory")
    workflow.add_edge("agent", "memory")
    workflow.add_edge("tools", "memory")
    workflow.add_conditional_edges(
        "memory",
        route_after_memory,
        {"agent": "agent", "tools": "tools", "orchestrator": "orchestrator", "evaluate": "evaluate"},
    )
    workflow.add_conditional_edges("evaluate", route_after_evaluation, {"end": END, "orchestrator": "orchestrator"})

    return workflow.compile(checkpointer=MemorySaver())

# ----------------- 极客终端交互 -----------------
async def main():
    agent_app = build_agent_graph()
    config = {
        "configurable": {"thread_id": str(uuid.uuid4())},
        "callbacks": [StreamingConsoleCallback()]
    }

    print("\n" + "="*70)
    logger.info("🚀 企业级 ReAct Tool-Calling Agent 已启动")
    logger.info("💡 指令: /clear 清空长期记忆 | /quit 退出")
    print("="*70)

    memory_messages = []

    while True:
        print("\n" + "-"*70)
        user_input = input("🧑 [请输入指令或问题]:\n> ").strip()

        if not user_input: continue
        if user_input.lower() in ['/quit', '/exit', '/q']: break
        if user_input.lower() == '/clear':
            memory_messages = []
            logger.info("🧹 \033[92m[记忆已清空]\033[0m")
            config["configurable"]["thread_id"] = str(uuid.uuid4())
            continue

        memory_messages = trim_messages(memory_messages, session_id="cli")
        memory_messages.append(HumanMessage(content=user_input))
        initial_input = {
            "messages": memory_messages,
            "revision_count": 0,
            "eval_status": "",
            "session_id": "cli",
            "task_complexity": "unknown",
            "todo_list": [],
            "context_tags": ["general"],
            "world_state": {},
            "orchestrator_next": "agent",
        }

        try:
            final_state = await agent_app.ainvoke(initial_input, config)
            memory_messages.append(final_state["messages"][-1])
            memory_messages = trim_messages(memory_messages, session_id="cli")
            logger.info("✨ 任务完成。")
        except Exception as e:
            logger.error(f"报错: {str(e)}")
            if memory_messages: memory_messages.pop()

if __name__ == "__main__":
    if sys.platform.startswith('win'):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
