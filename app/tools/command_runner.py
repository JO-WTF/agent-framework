import asyncio
import subprocess

from langchain_core.tools import tool
from langchain_core.runnables.config import RunnableConfig

from app.config import PROMPTS
from app.logging_config import logger
from app.memory.store import save_agent_note, summarize_text
from app.tools.context import get_session_id_from_config_or_context
from app.tools.sandbox import run_sandboxed_command, sandbox_enabled
from app.tools.storage import store_tool_result_for_current_session


@tool(description=PROMPTS["tools"]["run_command"])
async def run_command(command: str, config: RunnableConfig = None) -> str:
    get_session_id_from_config_or_context(config)
    logger.info(f"💻 \033[95m[触发工具: 执行命令] -> {command}\033[0m")
    try:
        loop = asyncio.get_event_loop()
        import contextvars
        ctx = contextvars.copy_context()
        result_obj = await loop.run_in_executor(None, lambda: ctx.run(run_sandboxed_command, command))
        out = result_obj.stdout
        err = result_obj.stderr

        result = []
        if out:
            result.append(f"标准输出:\n{out}")
        if err:
            result.append(f"标准错误:\n{err}")
        if sandbox_enabled() and result_obj.work_dir:
            result.append(f"沙箱工作目录:\n{result_obj.work_dir}")

        if not result:
            store_tool_result_for_current_session("run_command", "", {"command": command, "returncode": result_obj.returncode, **result_obj.metadata})
            return "命令执行成功 (无输出)。"

        text = "\n".join(result)
        ref_id = store_tool_result_for_current_session(
            "run_command",
            text,
            {"command": command, "returncode": result_obj.returncode, **result_obj.metadata},
        )
        if len(text) > 1024:
            summary = summarize_text(text, max_chars=512)
            return f"命令输出过长，已保存为引用 {ref_id}。\n如需完整内容，请调用 read_tool_result(ref_id=\"{ref_id}\")，必要时使用 offset/limit 分页。\n摘要:\n{summary}"
        return text
    except subprocess.TimeoutExpired:
        store_tool_result_for_current_session("run_command", "", {"command": command, "status": "timeout"})
        note_id = save_agent_note(f"run_command 超时：{command}", source="run_command", tags=["timeout", "tool_error"])
        return f"执行失败: 命令超时 (超过30秒)。已记录笔记 {note_id}。"
    except Exception as e:
        store_tool_result_for_current_session("run_command", str(e), {"command": command, "status": "error"})
        note_id = save_agent_note(f"run_command 失败：{command}\n错误: {str(e)}", source="run_command", tags=["tool_error"])
        return f"执行失败: {str(e)}。已记录笔记 {note_id}。"
