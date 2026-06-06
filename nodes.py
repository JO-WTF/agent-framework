import datetime
import json
import re
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_core.runnables.config import RunnableConfig
from langgraph.prebuilt import ToolNode
from config import llm_client, AgentState, PROMPTS
from tools import AGENT_TOOLS
from logger import logger

# 给大模型绑定物理工具
llm_with_tools = llm_client.bind_tools(AGENT_TOOLS)

# 官方预置的执行节点 (自动解析 JSON 并执行 tools.py 里的函数)
tools_execution_node = ToolNode(AGENT_TOOLS)

def get_system_prompt(prompt_key: str) -> str:
    current_date_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    global_prompt = PROMPTS.get("global_context", "").replace("{current_date}", current_date_str)
    specific_prompt = PROMPTS.get(prompt_key, "").replace("{current_date}", current_date_str)
    return f"{global_prompt}\n\n{specific_prompt}".strip()

def _silent_config(config: RunnableConfig) -> RunnableConfig:
    silent = dict(config or {})
    silent["callbacks"] = []
    return silent

def _parse_json_object(raw_text: str) -> dict:
    text = raw_text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise

def _format_todo_items(items: list[dict], indent: int = 0) -> list[str]:
    lines = []
    for item in items:
        status = item.get("status", "pending")
        item_id = item.get("id", "-")
        title = item.get("title", "")
        note = item.get("note", "")
        prefix = "  " * indent
        line = f"{prefix}- [{status}] {item_id} {title}".strip()
        if note:
            line = f"{line} ({note})"
        lines.append(line)
        children = item.get("children") or []
        if children:
            lines.extend(_format_todo_items(children, indent + 1))
    return lines

def _format_todo_context(state: AgentState) -> str:
    todo_list = state.get("todo_list") or []
    complexity = state.get("task_complexity", "simple")
    if not todo_list:
        return f"任务复杂度：{complexity}\n当前没有 todo list。"

    lines = _format_todo_items(todo_list)
    return f"任务复杂度：{complexity}\n当前 todo list：\n" + "\n".join(lines)

def _summarize_recent_messages(state: AgentState, limit: int = 8) -> str:
    summaries = []
    for message in state["messages"][-limit:]:
        role = message.__class__.__name__
        content = getattr(message, "content", "")
        tool_calls = getattr(message, "tool_calls", None)
        if tool_calls:
            content = f"{content}\n工具调用: {tool_calls}"
        summaries.append(f"{role}: {content}")
    return "\n\n".join(summaries)

def _default_orchestrator_next(state: AgentState) -> str:
    last_message = state["messages"][-1]
    if isinstance(last_message, AIMessage) and not getattr(last_message, "tool_calls", None):
        return "evaluate"
    return "agent"

# ----------------- 任务编排节点 -----------------
async def orchestrator_node(state: AgentState, config: RunnableConfig):
    logger.info("🧭 \033[94m[Node: Orchestrator]\033[0m 正在判断任务复杂度并更新 todo list...")
    system_prompt = get_system_prompt("orchestrator")
    current_todo_json = json.dumps(state.get("todo_list", []), ensure_ascii=False, indent=2)
    recent_messages = _summarize_recent_messages(state)

    response = await llm_client.ainvoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=(
            f"当前任务复杂度: {state.get('task_complexity', 'unknown')}\n\n"
            f"当前 todo_list JSON:\n{current_todo_json}\n\n"
            f"最近消息:\n{recent_messages}"
        ))
    ], _silent_config(config))

    try:
        parsed = _parse_json_object(response.content)
        complexity = parsed.get("task_complexity", state.get("task_complexity", "simple"))
        todo_list = parsed.get("todo_list", state.get("todo_list", []))
        next_node = parsed.get("next", _default_orchestrator_next(state))
        if next_node not in {"agent", "evaluate"}:
            next_node = _default_orchestrator_next(state)
    except Exception as exc:
        logger.warning(f"⚠️ \033[93m[Orchestrator]\033[0m JSON 解析失败，使用保守路由。原因: {exc}")
        complexity = state.get("task_complexity", "simple")
        todo_list = state.get("todo_list", [])
        next_node = _default_orchestrator_next(state)

    # 如果 Agent 已经给出自然语言回复且没有继续调用工具，必须进入质检。
    # 这里用确定性路由兜底，避免 Orchestrator LLM 误判后再次回到 Agent 造成重复回答。
    next_node = _default_orchestrator_next(state) if _default_orchestrator_next(state) == "evaluate" else next_node

    if todo_list:
        logger.info("\n".join(["📋 \033[94m[Todo]\033[0m"] + _format_todo_items(todo_list)))
    else:
        logger.info(f"📋 \033[94m[Todo]\033[0m 无，任务复杂度: {complexity}")

    return {
        "task_complexity": complexity,
        "todo_list": todo_list,
        "orchestrator_next": next_node,
    }

# ----------------- 核心大脑节点 -----------------
async def agent_reasoning_node(state: AgentState, config: RunnableConfig):
    logger.info("🧠 \033[92m[Node: Agent Brain]\033[0m 正在分析请求...")
    # 动态加载 YAML 提示词，包含全局信息
    system_prompt = (
        f"{get_system_prompt('agent_brain')}\n\n"
        f"【Orchestrator 任务计划】\n{_format_todo_context(state)}"
    )
    messages = [SystemMessage(content=system_prompt)] + state["messages"]
    response = await llm_with_tools.ainvoke(messages, config)
    return {"messages": [response]}

# ----------------- 宏观 QA 质检节点 -----------------
async def evaluate_response_node(state: AgentState, config: RunnableConfig):
    logger.info("🕵️ \033[93m[Node: Evaluator]\033[0m 质检员正在审查答复...")
    rev_count = state.get("revision_count", 0)
    
    if rev_count >= 3:
        logger.warning("⚠️ \033[91m[熔断]\033[0m 达最大重试，强制通过。")
        return {"eval_status": "PASS"}

    user_q = next((m.content for m in reversed(state["messages"][:-1]) if isinstance(m, HumanMessage)), "")
    draft_reply = state["messages"][-1].content
    
    system_prompt = get_system_prompt("evaluator")
    response = await llm_client.ainvoke([
        SystemMessage(content=system_prompt), 
        HumanMessage(content=(
            f"问题: {user_q}\n\n"
            f"Orchestrator todo 状态:\n{_format_todo_context(state)}\n\n"
            f"回复:\n{draft_reply}"
        ))
    ], _silent_config(config))
    eval_result = response.content.strip()
    
    if eval_result.startswith("REJECT"):
        reason = eval_result.replace("REJECT:", "").strip()
        logger.warning(f"❌ \033[35m[不合格]\033[0m 打回重做。原因: {reason}")
        reject_msg = HumanMessage(content=f"[质检打回] 回答不合格！原因：{reason}。请参考 todo list 重新规划下一步，并重新调用必要工具获取数据。")
        return {"eval_status": "REJECT", "revision_count": rev_count + 1, "messages": [reject_msg]}
    
    logger.info("✅ \033[92m[合格]\033[0m 准备输出。")
    return {"eval_status": "PASS"}
