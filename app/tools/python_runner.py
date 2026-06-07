import contextlib
import io
import traceback

from langchain_core.tools import tool

from app.config import PROMPTS
from app.logging_config import logger
from app.memory.store import save_agent_note, summarize_text
from app.tools.storage import store_tool_result_for_current_session


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
        ref_id = store_tool_result_for_current_session("run_python", out, {"source": "run_python"})
        if out and len(out) > 1024:
            summary = summarize_text(out, max_chars=512)
            return f"Python 输出过长，已保存为引用 {ref_id}。\n摘要:\n{summary}"
        return out if out else "代码执行成功 (无 print 输出)。"
    except Exception:
        err = traceback.format_exc()
        store_tool_result_for_current_session("run_python", err, {"source": "run_python", "status": "error"})
        save_agent_note(f"run_python 失败，错误摘要: {err.splitlines()[:6]}", source="run_python", tags=["tool_error"])
        return f"代码报错:\n{err}"
