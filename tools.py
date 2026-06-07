import io
import asyncio
import contextlib
import traceback
import subprocess
from contextvars import ContextVar
from langchain_core.tools import tool
from config import search_client, PROMPTS
from logger import logger
from memory_utils import save_agent_note, store_tool_result, summarize_text

# Context variable to pass session_id to tools
_session_id: ContextVar[str | None] = ContextVar("_session_id", default=None)


def set_session_id(session_id: str | None) -> None:
    """Set the current session ID for tool execution."""
    _session_id.set(session_id)


def get_session_id() -> str | None:
    """Get the current session ID."""
    return _session_id.get()


def _store_tool_result_with_session(tool_name: str, raw_output: str, metadata: dict | None = None) -> str:
    """Wrapper to store tool result with automatic session ID."""
    session_id = get_session_id()
    if not session_id:
        # Fallback for CLI mode - use a default session
        session_id = "cli"
        set_session_id(session_id)
    return store_tool_result(tool_name, raw_output, session_id=session_id, metadata=metadata)

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
        if out and len(out) > 1024:
            ref_id = _store_tool_result_with_session("run_python", out, {"source": "run_python"})
            summary = summarize_text(out, max_chars=512)
            return f"Python 输出过长，已保存为引用 {ref_id}。\n摘要:\n{summary}"
        return out if out else "代码执行成功 (无 print 输出)。"
    except Exception:
        err = traceback.format_exc()
        save_agent_note(f"run_python 失败，错误摘要: {err.splitlines()[:6]}", source="run_python", tags=["tool_error"])
        return f"代码报错:\n{err}"

# 3. CLI 终端执行工具
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
        if out:
            result.append(f"标准输出:\n{out}")
        if err:
            result.append(f"标准错误:\n{err}")

        if not result:
            return "命令执行成功 (无输出)。"

        text = "\n".join(result)
        if len(text) > 1024:
            ref_id = _store_tool_result_with_session("run_command", text, {"command": command})
            summary = summarize_text(text, max_chars=512)
            return f"命令输出过长，已保存为引用 {ref_id}。\n摘要:\n{summary}"
        return text
    except subprocess.TimeoutExpired:
        note_id = save_agent_note(f"run_command 超时：{command}", source="run_command", tags=["timeout", "tool_error"])
        return f"执行失败: 命令超时 (超过30秒)。已记录笔记 {note_id}。"
    except Exception as e:
        note_id = save_agent_note(f"run_command 失败：{command}\n错误: {str(e)}", source="run_command", tags=["tool_error"])
        return f"执行失败: {str(e)}。已记录笔记 {note_id}。"

# 导出工具集
AGENT_TOOLS = [search_web, run_python, run_command]
