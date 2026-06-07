import asyncio
import subprocess

from langchain_core.tools import tool

from app.config import PROMPTS
from app.logging_config import logger
from app.memory.store import save_agent_note, summarize_text
from app.tools.storage import store_tool_result_for_current_session


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
            store_tool_result_for_current_session("run_command", "", {"command": command, "returncode": process.returncode})
            return "命令执行成功 (无输出)。"

        text = "\n".join(result)
        ref_id = store_tool_result_for_current_session(
            "run_command",
            text,
            {"command": command, "returncode": process.returncode},
        )
        if len(text) > 1024:
            summary = summarize_text(text, max_chars=512)
            return f"命令输出过长，已保存为引用 {ref_id}。\n摘要:\n{summary}"
        return text
    except subprocess.TimeoutExpired:
        store_tool_result_for_current_session("run_command", "", {"command": command, "status": "timeout"})
        note_id = save_agent_note(f"run_command 超时：{command}", source="run_command", tags=["timeout", "tool_error"])
        return f"执行失败: 命令超时 (超过30秒)。已记录笔记 {note_id}。"
    except Exception as e:
        store_tool_result_for_current_session("run_command", str(e), {"command": command, "status": "error"})
        note_id = save_agent_note(f"run_command 失败：{command}\n错误: {str(e)}", source="run_command", tags=["tool_error"])
        return f"执行失败: {str(e)}。已记录笔记 {note_id}。"
