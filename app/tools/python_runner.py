import asyncio
import subprocess

from langchain_core.tools import tool
from langchain_core.runnables.config import RunnableConfig

from app.config import PROMPTS
from app.logging_config import logger
from app.memory.store import save_agent_note, summarize_text
from app.tools.context import get_session_id_from_config_or_context
from app.tools.sandbox import run_sandboxed_python
from app.tools.storage import store_tool_result_for_current_session


@tool(description=PROMPTS["tools"]["run_python"])
async def run_python(code: str, config: RunnableConfig = None) -> str:
    get_session_id_from_config_or_context(config)
    logger.info("🐍 \033[96m[触发工具: 动态沙箱] -> 执行计算代码\033[0m")
    logger.debug(f"\033[90m{'-'*40}\n{code}\n{'-'*40}\033[0m")
    try:
        loop = asyncio.get_event_loop()
        import contextvars
        ctx = contextvars.copy_context()
        result_obj = await loop.run_in_executor(None, lambda: ctx.run(run_sandboxed_python, code))
        parts = []
        if result_obj.stdout:
            parts.append(result_obj.stdout)
        if result_obj.stderr:
            parts.append(f"标准错误:\n{result_obj.stderr}")
        if result_obj.work_dir:
            parts.append(f"沙箱工作目录:\n{result_obj.work_dir}")
        out = "\n".join(parts).strip()
        ref_id = store_tool_result_for_current_session(
            "run_python",
            out,
            {"source": "run_python", "returncode": result_obj.returncode, **result_obj.metadata},
        )
        if result_obj.returncode != 0:
            return f"代码报错:\n{out}"
        if out and len(out) > 1024:
            summary = summarize_text(out, max_chars=512)
            return f"Python 输出过长，已保存为引用 {ref_id}。\n如需完整内容，请调用 read_tool_result(ref_id=\"{ref_id}\")，必要时使用 offset/limit 分页。\n摘要:\n{summary}"
        return out if out else "代码执行成功 (无 print 输出)。"
    except subprocess.TimeoutExpired:
        store_tool_result_for_current_session("run_python", "", {"source": "run_python", "status": "timeout"})
        save_agent_note("run_python 沙箱执行超时", source="run_python", tags=["timeout", "tool_error"])
        return "代码报错:\n执行失败: Python 沙箱执行超时。"
    except Exception as e:
        store_tool_result_for_current_session("run_python", str(e), {"source": "run_python", "status": "error"})
        save_agent_note(f"run_python 沙箱执行失败: {str(e)}", source="run_python", tags=["tool_error"])
        return f"代码报错:\n执行失败: {str(e)}"
