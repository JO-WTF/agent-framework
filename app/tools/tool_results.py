import json

from langchain_core.tools import tool
from langchain_core.runnables.config import RunnableConfig

from app.config import PROMPTS
from app.tools.context import get_session_id_from_config_or_context
from app.tools.storage import list_tool_results_for_current_session, read_tool_result_for_current_session


@tool(description=PROMPTS["tools"]["list_tool_results"])
async def list_tool_results(limit: int = 10, config: RunnableConfig = None) -> str:
    get_session_id_from_config_or_context(config)
    records = list_tool_results_for_current_session(limit=limit)
    if not records:
        return "当前会话没有已归档的工具结果。"
    return json.dumps(records, ensure_ascii=False, indent=2)


@tool(description=PROMPTS["tools"]["read_tool_result"])
async def read_tool_result(ref_id: str, offset: int = 0, limit: int = 8000, config: RunnableConfig = None) -> str:
    get_session_id_from_config_or_context(config)
    try:
        result = read_tool_result_for_current_session(ref_id=ref_id, offset=offset, limit=limit)
    except Exception as e:
        return f"执行失败: 读取工具结果失败: {str(e)}"

    header = (
        f"工具结果 {result['id']} ({result['tool_name']})\n"
        f"offset={result['offset']} limit={result['limit']} "
        f"content_length={result['content_length']} has_more={str(result['has_more']).lower()}"
    )
    if result["has_more"]:
        header += f" next_offset={result['next_offset']}"
    if result["offset"] >= result["content_length"]:
        return f"{header}\n\n已到达工具结果末尾，没有更多内容。"
    return f"{header}\n\n{result['content']}"
