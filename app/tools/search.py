import asyncio

from langchain_core.tools import tool

from app.config import PROMPTS, search_client
from app.logging_config import logger
from app.tools.storage import store_tool_result_for_current_session


@tool(description=PROMPTS["tools"]["search_web"])
async def search_web(query: str) -> str:
    logger.info(f"🌐 \033[94m[触发工具: 联网检索] -> {query}\033[0m")
    try:
        loop = asyncio.get_event_loop()
        res = await loop.run_in_executor(None, lambda: search_client.search(query=query, max_results=3))
        results = [f"- {r['title']}: {r['content']}" for r in res.get("results", [])]
        text = "\n".join(results) if results else "未找到相关结果。"
        store_tool_result_for_current_session("search_web", text, {"query": query, "result_count": len(results)})
        return text
    except Exception as e:
        text = f"搜索失败: {str(e)}"
        store_tool_result_for_current_session("search_web", text, {"query": query, "status": "error"})
        return text
