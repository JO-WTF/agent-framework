import io
import asyncio
import contextlib
import traceback
import subprocess
from langchain_core.tools import tool
from config import search_client, PROMPTS
from logger import logger

# 1. 网络搜索工具
@tool(description=PROMPTS["tools"]["search_web"])
async def search_web(query: str) -> str:
    logger.info(f"🌐 \033[94m[触发工具: 联网检索] -> {query}\033[0m")
    try:
        loop = asyncio.get_event_loop()
        res = await loop.run_in_executor(None, lambda: search_client.search(query=query, max_results=3))
        results = [f"- {r['title']}: {r['content']}" for r in res.get("results", [])]
        return "\n".join(results) if results else "未找到相关结果。"
    except Exception as e:
        return f"搜索失败: {str(e)}"

# 2. Python 沙箱工具
@tool(description=PROMPTS["tools"]["run_python"])
async def run_python(code: str) -> str:
    logger.info("🐍 \033[96m[触发工具: 动态沙箱] -> 执行计算代码\033[0m")
    logger.debug(f"\033[90m{'-'*40}\n{code}\n{'-'*40}\033[0m")
    output_buffer = io.StringIO()
    namespace = {} 
    try:
        with contextlib.redirect_stdout(output_buffer):
            exec(code, namespace)
        out = output_buffer.getvalue().strip()
        return out if out else "代码执行成功 (无 print 输出)。"
    except Exception:
        return f"代码报错:\n{traceback.format_exc()}"

# 3. 模拟业务：查询客户订单
@tool(description=PROMPTS["tools"]["query_customer_order"])
async def query_customer_order(order_id: str) -> str:
    logger.info(f"📦 \033[93m[触发工具: 客单查询(PO)] -> {order_id}\033[0m")
    return f"客户订单 {order_id} 状态：已确认，工厂排产中。"

# 4. 模拟业务：查询运输订单 (带有黑话对齐)
@tool(description=PROMPTS["tools"]["query_transport_order"])
async def query_transport_order(order_id: str) -> str:
    logger.info(f"🚚 \033[93m[触发工具: 物流查询(DN)] -> {order_id}\033[0m")
    return f"运输订单 {order_id} 状态：已发车，预计明天送达。"

# 5. CLI 终端执行工具
@tool(description=PROMPTS["tools"]["run_command"])
async def run_command(command: str) -> str:
    logger.info(f"💻 \033[95m[触发工具: 执行命令] -> {command}\033[0m")
    try:
        loop = asyncio.get_event_loop()
        process = await loop.run_in_executor(
            None, 
            lambda: subprocess.run(
                command, 
                shell=True, 
                capture_output=True, 
                text=True, 
                timeout=30
            )
        )
        out = process.stdout.strip()
        err = process.stderr.strip()
        
        result = []
        if out: result.append(f"标准输出:\n{out}")
        if err: result.append(f"标准错误:\n{err}")
        
        if not result:
            return "命令执行成功 (无输出)。"
        return "\n".join(result)
    except subprocess.TimeoutExpired:
        return "执行失败: 命令超时 (超过30秒)。"
    except Exception as e:
        return f"执行失败: {str(e)}"

# 导出工具集
AGENT_TOOLS = [search_web, run_python, query_customer_order, query_transport_order, run_command]