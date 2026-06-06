import datetime
from langchain_core.messages import SystemMessage, HumanMessage
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

# ----------------- 核心大脑节点 -----------------
async def agent_reasoning_node(state: AgentState, config: RunnableConfig):
    logger.info("🧠 \033[92m[Node: Agent Brain]\033[0m 正在分析请求...")
    # 动态加载 YAML 提示词，包含全局信息
    system_prompt = get_system_prompt("agent_brain")
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
        HumanMessage(content=f"问题: {user_q}\n\n回复:\n{draft_reply}")
    ], config)
    eval_result = response.content.strip()
    
    if eval_result.startswith("REJECT"):
        reason = eval_result.replace("REJECT:", "").strip()
        logger.warning(f"❌ \033[35m[不合格]\033[0m 打回重做。原因: {reason}")
        reject_msg = HumanMessage(content=f"[质检打回] 回答不合格！原因：{reason}。请重新调用工具获取数据。")
        return {"eval_status": "REJECT", "revision_count": rev_count + 1, "messages": [reject_msg]}
    
    logger.info("✅ \033[92m[合格]\033[0m 准备输出。")
    return {"eval_status": "PASS"}