import json

from langchain_core.tools import tool
from langchain_core.runnables.config import RunnableConfig

from app.config import PROMPTS
from app.logging_config import logger
from app.memory.store import save_agent_note
from app.tools.approvals import create_file_writeback_approval, create_filesystem_access_approval
from app.tools.context import get_session_id_from_config_or_context, ensure_session_id
from app.tools.sandbox import (
    SandboxError,
    get_session_sandbox_status,
    start_session_sandbox,
    stop_session_sandbox,
)
from app.tools.storage import store_tool_result_for_current_session


def _format_status(status: dict[str, str]) -> str:
    return json.dumps(status, ensure_ascii=False, indent=2)


@tool(description=PROMPTS["tools"]["start_sandbox"])
async def start_sandbox(config: RunnableConfig = None) -> str:
    get_session_id_from_config_or_context(config)
    logger.info("📦 \033[95m[触发工具: 启动会话沙箱]\033[0m")

    try:
        status = start_session_sandbox()
        text = f"会话沙箱已就绪:\n{_format_status(status)}"
        store_tool_result_for_current_session("start_sandbox", text, status)
        return text
    except Exception as e:
        store_tool_result_for_current_session("start_sandbox", str(e), {"status": "error"})
        note_id = save_agent_note(f"start_sandbox 失败: {str(e)}", source="start_sandbox", tags=["tool_error", "sandbox"])
        return f"启动沙箱失败: {str(e)}。已记录笔记 {note_id}。"


@tool(description=PROMPTS["tools"]["sandbox_status"])
async def sandbox_status(config: RunnableConfig = None) -> str:
    get_session_id_from_config_or_context(config)
    logger.info("📦 \033[95m[触发工具: 查看会话沙箱状态]\033[0m")
    try:
        status = get_session_sandbox_status()
        text = f"会话沙箱状态:\n{_format_status(status)}"
        store_tool_result_for_current_session("sandbox_status", text, status)
        return text
    except Exception as e:
        store_tool_result_for_current_session("sandbox_status", str(e), {"status": "error"})
        return f"读取沙箱状态失败: {str(e)}"


@tool(description=PROMPTS["tools"]["stop_sandbox"])
async def stop_sandbox(config: RunnableConfig = None) -> str:
    get_session_id_from_config_or_context(config)
    logger.info("📦 \033[95m[触发工具: 停止会话沙箱]\033[0m")

    try:
        status = stop_session_sandbox()
        text = f"会话沙箱已停止:\n{_format_status(status)}"
        store_tool_result_for_current_session("stop_sandbox", text, status)
        return text
    except Exception as e:
        store_tool_result_for_current_session("stop_sandbox", str(e), {"status": "error"})
        note_id = save_agent_note(f"stop_sandbox 失败: {str(e)}", source="stop_sandbox", tags=["tool_error", "sandbox"])
        return f"停止沙箱失败: {str(e)}。已记录笔记 {note_id}。"


@tool(description=PROMPTS["tools"]["apply_sandbox_file"])
async def apply_sandbox_file(source_path: str, target_path: str, overwrite: bool = False, config: RunnableConfig = None) -> str:
    session_id = get_session_id_from_config_or_context(config)
    logger.info(f"📦 \033[95m[触发工具: 申请写回沙箱文件] -> {source_path} => {target_path}\033[0m")
    try:
        result = create_file_writeback_approval(
            session_id,
            source_path,
            target_path,
            overwrite=overwrite,
        )
        text = (
            "沙箱文件写回申请已创建，等待用户在前端批准后才会写入项目:\n"
            f"{_format_status(result)}"
        )
        store_tool_result_for_current_session("apply_sandbox_file", text, result)
        return text
    except SandboxError as e:
        store_tool_result_for_current_session("apply_sandbox_file", str(e), {"status": "rejected"})
        return f"执行失败: 写回被拒绝: {str(e)}"
    except Exception as e:
        store_tool_result_for_current_session("apply_sandbox_file", str(e), {"status": "error"})
        note_id = save_agent_note(f"apply_sandbox_file 失败: {str(e)}", source="apply_sandbox_file", tags=["tool_error", "sandbox"])
        return f"写回失败: {str(e)}。已记录笔记 {note_id}。"


@tool("add_shared_mount", description=PROMPTS["tools"]["add_shared_mount"])
async def add_shared_mount_tool(name: str, host_path: str, access: str = "read", config: RunnableConfig = None) -> str:
    session_id = get_session_id_from_config_or_context(config)
    logger.info(f"📦 \033[95m[触发工具: 申请共享目录访问] -> {name}: {host_path} (access: {access})\033[0m")
    try:
        result = create_filesystem_access_approval(session_id, name=name, host_path=host_path, access=access)
        text = (
            f"共享目录{'读取' if access == 'read' else '读写'}申请已创建，等待用户在前端批准后才会授权挂载。若当前会话容器已经启动，批准后将自动重新启动沙箱以使挂载生效:\n"
            f"{_format_status(result)}"
        )
        store_tool_result_for_current_session("add_shared_mount", text, result)
        return text
    except SandboxError as e:
        store_tool_result_for_current_session("add_shared_mount", str(e), {"status": "rejected"})
        return f"执行失败: 共享目录授权被拒绝: {str(e)}"
    except Exception as e:
        store_tool_result_for_current_session("add_shared_mount", str(e), {"status": "error"})
        note_id = save_agent_note(f"add_shared_mount 失败: {str(e)}", source="add_shared_mount", tags=["tool_error", "sandbox"])
        return f"添加共享目录失败: {str(e)}。已记录笔记 {note_id}。"
