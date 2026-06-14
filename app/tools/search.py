import asyncio

from langchain_core.tools import tool
from langchain_core.runnables.config import RunnableConfig

from app.config import PROMPTS, search_client
from app.logging_config import logger
from app.tools.context import get_session_id_from_config_or_context
from app.tools.storage import store_tool_result_for_current_session


@tool(description=PROMPTS["tools"]["search_web"])
async def search_web(query: str, config: RunnableConfig = None) -> str:
    get_session_id_from_config_or_context(config)
    logger.info(f"🌐 \033[94m[触发工具: 联网检索] -> {query}\033[0m")
    try:
        loop = asyncio.get_event_loop()
        res = await loop.run_in_executor(None, lambda: search_client.search(query=query, max_results=3))
        results = []
        for item in res.get("results", []):
            title = item.get("title", "(无标题)")
            url = item.get("url", "")
            content = item.get("content", "")
            source = f"\n  来源: {url}" if url else ""
            results.append(f"- {title}: {content}{source}")
        text = "\n".join(results) if results else "未找到相关结果。"
        store_tool_result_for_current_session("search_web", text, {"query": query, "result_count": len(results)})
        return text
    except Exception as e:
        text = f"搜索失败: {str(e)}"
        store_tool_result_for_current_session("search_web", text, {"query": query, "status": "error"})
        return text
