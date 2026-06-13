import json
import re
import shlex
from typing import Any
from typing_extensions import NotRequired, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables.config import RunnableConfig
from langgraph.graph import END, START, StateGraph

from app.config import PROMPTS, llm_client
from app.llm_logging import log_llm_request, log_llm_response
from app.logging_config import logger
from app.tools.context import set_session_id
from app.tools.registry import AGENT_TOOLS
from app.tools.reference_resolver import resolve_tool_args


class ToolExecutionState(TypedDict):
    """Private state for one isolated tool-call execution."""

    original_request: dict[str, Any]
    tool_call_id: str
    tool_name: str
    args: dict[str, Any]
    session_id: str
    retry_count: int
    max_retries: int
    internal_messages: list[dict[str, Any]]
    status: str
    final_result: str
    last_result: NotRequired[str]
    last_error: NotRequired[str]
    failure_reason: NotRequired[str]
    fix_explanation: NotRequired[str]
    required_action: NotRequired[dict[str, Any]]


TOOLS_BY_NAME = {tool.name: tool for tool in AGENT_TOOLS}
FALLBACK_FIX_ARGS_PROMPT = """你是工具调用参数修复器。你不是在回答用户问题，只负责修复一次工具调用的参数。

请严格输出 JSON，不要输出 Markdown，不要解释。JSON schema:
{
  "can_retry": true 或 false,
  "args": {"参数名": "修复后的参数值"},
  "reason": "简短说明为什么这样修复"
}

约束：
1. 不要改变工具名称。
2. 不要引入与原始请求无关的新目标。
3. 不要扩大工具调用权限或风险。
4. 对 run_command，不允许把只读命令改成写操作。
5. 对 run_command，不允许加入 sudo、rm、chmod -R、curl|sh、wget|sh 等危险命令。
6. 如果无法安全修复，返回 can_retry=false。
"""
DANGEROUS_COMMAND_PATTERNS = (
    r"\bsudo\b",
    r"\brm\b",
    r"\bchmod\b.*\b-R\b",
    r"\bchown\b",
    r"\bmkfs\b",
    r"\bdd\b",
    r"\bshutdown\b",
    r"\breboot\b",
    r"curl\b.*\|\s*(sh|bash)",
    r"wget\b.*\|\s*(sh|bash)",
    r">\s*/",
)
MUTATING_COMMANDS = {
    "cp",
    "mv",
    "rm",
    "touch",
    "mkdir",
    "rmdir",
    "tee",
    "chmod",
    "chown",
    "git",
    "pip",
    "python",
    "python3",
    "npm",
    "yarn",
    "pnpm",
}
READ_ONLY_COMMANDS = {
    "cat",
    "printf",
    "echo",
    "pwd",
    "ls",
    "find",
    "rg",
    "grep",
    "head",
    "tail",
    "sed",
    "awk",
    "wc",
    "sort",
    "uniq",
    "date",
    "whoami",
}


def _append_internal_message(state: ToolExecutionState, message: dict[str, Any]) -> list[dict[str, Any]]:
    return [*state.get("internal_messages", []), message]


def get_max_retries(tool_name: str) -> int:
    """Return a conservative retry budget per tool."""
    if tool_name == "run_python":
        return 3
    if tool_name == "search_web":
        return 1
    if tool_name == "run_command":
        return 1
    return 0


def extract_missing_python_dependency(error_text: str) -> str | None:
    """Extract a missing import/package name from Python traceback text."""
    patterns = (
        r"ModuleNotFoundError: No module named ['\"]([^'\"]+)['\"]",
        r"ImportError: No module named ['\"]([^'\"]+)['\"]",
        r"No module named ['\"]([^'\"]+)['\"]",
    )
    for pattern in patterns:
        match = re.search(pattern, error_text)
        if match:
            return match.group(1).split(".")[0]
    return None


def build_dependency_required_action(package_name: str | None) -> dict[str, Any]:
    package = package_name or "<missing-package>"
    return {
        "type": "install_python_package",
        "package": package,
        "suggested_tool": "run_command",
        "command": f"pip install {package}" if package_name else "pip install <missing-package>",
        "requires_confirmation": True,
        "requires_sandbox": True,
    }


def is_python_dependency_missing(error_text: str) -> bool:
    return bool(extract_missing_python_dependency(error_text)) or "ModuleNotFoundError" in error_text


def classify_tool_result(tool_name: str, result: str) -> tuple[str, str]:
    """Classify a tool result into a routing status and human-readable reason."""
    text = result or ""
    lower_text = text.lower()

    if tool_name == "run_python":
        if "代码报错:" in text or "traceback" in lower_text:
            if is_python_dependency_missing(text):
                package_name = extract_missing_python_dependency(text)
                package_hint = f" {package_name}" if package_name else ""
                return "needs_external_action", f"Python 缺少依赖{package_hint}，需要主图决定是否在隔离环境中安装。"
            retryable_python_markers = (
                "SyntaxError",
                "NameError",
                "TypeError",
                "ValueError",
            )
            if any(marker in text for marker in retryable_python_markers):
                return "retryable_failure", "Python 代码错误，可尝试修复代码参数。"
            if "ImportError" in text:
                return "needs_external_action", "Python import 失败，可能需要主图确认依赖或环境动作。"
            return "retryable_failure", "Python 执行报错，可尝试修复代码参数。"
        return "success", ""

    if tool_name == "search_web":
        if "搜索失败:" in text:
            terminal_markers = ("api key", "apikey", "unauthorized", "forbidden", "401", "403")
            if any(marker in lower_text for marker in terminal_markers):
                return "terminal_failure", "搜索服务鉴权或配置失败，不能通过改写查询修复。"
            return "retryable_failure", "搜索失败，可尝试改写查询。"
        if text.strip() == "未找到相关结果。":
            return "retryable_failure", "搜索无结果，可尝试改写查询。"
        return "success", ""

    if tool_name == "run_command":
        if "执行失败:" in text or "命令超时" in text:
            if "命令超时" in text:
                return "terminal_failure", "命令超时，不自动重试以避免重复执行风险。"
            return "retryable_failure", "命令执行失败，可尝试一次安全参数修复。"
        if any(marker in lower_text for marker in ("command not found", "no such file or directory", "syntax error")):
            return "retryable_failure", "命令输出包含 shell 错误，可尝试一次安全参数修复。"
        return "success", ""

    generic_failure_markers = ("执行失败:", "代码报错:", "搜索失败:", "Traceback", "Exception", "Error:", "错误:", "失败")
    if any(marker in text for marker in generic_failure_markers):
        return "retryable_failure", "工具返回失败信息。"
    return "success", ""


def _summarize_internal_messages(messages: list[dict[str, Any]], limit: int = 5, max_chars: int = 2000) -> str:
    recent_messages = messages[-limit:]
    summary = json.dumps(recent_messages, ensure_ascii=False, default=str)
    if len(summary) > max_chars:
        return f"{summary[:max_chars]}...（已截断）"
    return summary


def _extract_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    fenced_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.S)
    if fenced_match:
        cleaned = fenced_match.group(1)
    elif not cleaned.startswith("{"):
        object_match = re.search(r"\{.*\}", cleaned, re.S)
        if object_match:
            cleaned = object_match.group(0)
    parsed = json.loads(cleaned)
    if not isinstance(parsed, dict):
        raise ValueError("修复器返回的 JSON 顶层必须是对象")
    return parsed


def _command_head(command: str) -> str:
    try:
        parts = shlex.split(command)
    except ValueError:
        parts = command.split()
    return parts[0] if parts else ""


def _is_dangerous_command(command: str) -> bool:
    return any(re.search(pattern, command, flags=re.I) for pattern in DANGEROUS_COMMAND_PATTERNS)


def _command_risk(command: str) -> int:
    if _is_dangerous_command(command):
        return 3
    head = _command_head(command)
    if head in MUTATING_COMMANDS:
        return 2
    if head in READ_ONLY_COMMANDS:
        return 0
    return 1


def validate_fixed_args(tool_name: str, original_args: dict[str, Any], fixed_args: dict[str, Any]) -> tuple[bool, str]:
    """Validate LLM-proposed tool arguments before retrying."""
    if not isinstance(fixed_args, dict):
        return False, "修复后的 args 必须是对象。"

    tool = TOOLS_BY_NAME.get(tool_name)
    if tool and getattr(tool, "args_schema", None):
        try:
            tool.args_schema.model_validate(fixed_args)
        except Exception as exc:
            return False, f"修复后的参数不符合工具 schema: {exc}"

    if tool_name != "run_command":
        return True, ""

    original_command = str(original_args.get("command", ""))
    fixed_command = str(fixed_args.get("command", ""))
    if not fixed_command.strip():
        return False, "修复后的 command 不能为空。"
    if _is_dangerous_command(fixed_command):
        return False, "修复后的命令包含危险操作，已拒绝自动重试。"
    if _command_risk(fixed_command) > _command_risk(original_command):
        return False, "修复后的命令风险高于原始命令，已拒绝自动重试。"
    return True, ""


async def execute_node(state: ToolExecutionState, config: RunnableConfig) -> dict[str, Any]:
    """Execute a single tool call inside the private subgraph state."""
    tool_name = state["tool_name"]
    args = state.get("args", {})
    session_id = state.get("session_id", "cli")
    set_session_id(session_id)

    tool = TOOLS_BY_NAME.get(tool_name)
    if not tool:
        error_text = f"工具执行失败: 未找到工具 {tool_name}。"
        logger.warning(error_text)
        return {
            "status": "unknown_tool",
            "last_error": error_text,
            "failure_reason": "未知工具，无法执行或修复。",
            "final_result": error_text,
            "internal_messages": _append_internal_message(
                state,
                {
                    "type": "tool_error",
                    "attempt": state.get("retry_count", 0),
                    "tool_name": tool_name,
                    "args": args,
                    "content": error_text,
                },
            ),
        }

    try:
        resolved_args = resolve_tool_args(args)
        result = await tool.ainvoke(resolved_args, config=config)
        result_text = str(result)
        status, failure_reason = classify_tool_result(tool_name, result_text)
        required_action = (
            build_dependency_required_action(extract_missing_python_dependency(result_text))
            if tool_name == "run_python" and status == "needs_external_action"
            else None
        )
        message_type = "tool_result" if status == "success" else "tool_error"
        return {
            "status": status,
            "last_result": result_text,
            "last_error": result_text if status != "success" else "",
            "failure_reason": failure_reason,
            "required_action": required_action or {},
            "final_result": result_text,
            "internal_messages": _append_internal_message(
                state,
                {
                    "type": message_type,
                    "attempt": state.get("retry_count", 0),
                    "tool_name": tool_name,
                    "args": args,
                    "status": status,
                    "failure_reason": failure_reason,
                    "required_action": required_action or {},
                    "content": result_text,
                },
            ),
        }
    except Exception as exc:
        error_text = f"工具执行异常: {exc}"
        logger.exception("工具执行子图捕获异常: %s", tool_name)
        status, failure_reason = classify_tool_result(tool_name, error_text)
        if status == "success":
            status = "retryable_failure"
            failure_reason = "工具执行抛出异常，可尝试修复参数。"
        required_action = (
            build_dependency_required_action(extract_missing_python_dependency(error_text))
            if tool_name == "run_python" and status == "needs_external_action"
            else None
        )
        return {
            "status": status,
            "last_error": error_text,
            "failure_reason": failure_reason,
            "required_action": required_action or {},
            "final_result": error_text,
            "internal_messages": _append_internal_message(
                state,
                {
                    "type": "tool_error",
                    "attempt": state.get("retry_count", 0),
                    "tool_name": tool_name,
                    "args": args,
                    "status": status,
                    "failure_reason": failure_reason,
                    "required_action": required_action or {},
                    "content": error_text,
                },
            ),
        }


async def fix_node(state: ToolExecutionState, config: RunnableConfig) -> dict[str, Any]:
    """Ask an LLM to repair tool arguments, then validate the proposed args."""
    tool_name = state["tool_name"]
    current_args = state.get("args", {})
    retry_count = state.get("retry_count", 0)
    max_retries = state.get("max_retries", get_max_retries(tool_name))
    prompt = PROMPTS.get("tool_execution", {}).get("fix_args", FALLBACK_FIX_ARGS_PROMPT)
    error_context = state.get("last_error") or state.get("last_result") or state.get("failure_reason", "")

    messages = [
        SystemMessage(content=prompt),
        HumanMessage(
            content=(
                f"工具名称: {tool_name}\n"
                f"原始 tool call: {json.dumps(state.get('original_request', {}), ensure_ascii=False, default=str)}\n"
                f"当前参数: {json.dumps(current_args, ensure_ascii=False, default=str)}\n"
                f"失败原因: {state.get('failure_reason', '')}\n"
                f"最近错误或结果: {error_context}\n"
                f"内部历史摘要: {_summarize_internal_messages(state.get('internal_messages', []))}\n"
                f"当前重试次数: {retry_count}\n"
                f"最大重试次数: {max_retries}\n"
            )
        ),
    ]

    try:
        log_llm_request("tool_fix_args", messages)
        response = await llm_client.ainvoke(messages, config={**config, "callbacks": []})
        log_llm_response("tool_fix_args", response)
        response_text = str(getattr(response, "content", response))
        payload = _extract_json_object(response_text)
    except Exception as exc:
        final_result = (
            "工具执行失败，且自动修复参数失败。\n"
            f"失败原因: {state.get('failure_reason', '')}\n"
            f"修复器错误: {exc}\n"
            f"最后一次错误或结果:\n{error_context}"
        )
        return {
            "status": "terminal_failure",
            "final_result": final_result,
            "fix_explanation": f"修复器调用或解析失败: {exc}",
            "internal_messages": _append_internal_message(
                state,
                {
                    "type": "fix_error",
                    "attempt": retry_count,
                    "tool_name": tool_name,
                    "content": str(exc),
                },
            ),
        }

    can_retry = bool(payload.get("can_retry"))
    fixed_args = payload.get("args")
    reason = str(payload.get("reason", ""))
    if not can_retry:
        final_result = (
            "工具执行失败，自动修复器判断不应继续重试。\n"
            f"失败原因: {state.get('failure_reason', '')}\n"
            f"修复器说明: {reason}\n"
            f"最后一次错误或结果:\n{error_context}"
        )
        return {
            "status": "terminal_failure",
            "final_result": final_result,
            "fix_explanation": reason,
            "internal_messages": _append_internal_message(
                state,
                {
                    "type": "fix_declined",
                    "attempt": retry_count,
                    "tool_name": tool_name,
                    "content": reason,
                },
            ),
        }

    is_valid, validation_error = validate_fixed_args(tool_name, current_args, fixed_args)
    if not is_valid:
        final_result = (
            "工具执行失败，自动修复后的参数未通过校验。\n"
            f"失败原因: {state.get('failure_reason', '')}\n"
            f"校验错误: {validation_error}\n"
            f"修复器说明: {reason}\n"
            f"最后一次错误或结果:\n{error_context}"
        )
        return {
            "status": "terminal_failure",
            "final_result": final_result,
            "fix_explanation": reason,
            "internal_messages": _append_internal_message(
                state,
                {
                    "type": "fix_rejected",
                    "attempt": retry_count,
                    "tool_name": tool_name,
                    "old_args": current_args,
                    "new_args": fixed_args,
                    "reason": reason,
                    "validation_error": validation_error,
                },
            ),
        }

    return {
        "status": "retrying",
        "args": fixed_args,
        "retry_count": retry_count + 1,
        "fix_explanation": reason,
        "internal_messages": _append_internal_message(
            state,
            {
                "type": "fix",
                "attempt": retry_count,
                "tool_name": tool_name,
                "old_args": current_args,
                "new_args": fixed_args,
                "reason": reason,
            },
        ),
    }


async def finalize_node(state: ToolExecutionState) -> dict[str, Any]:
    """Normalize the result that will be exposed to the parent graph."""
    final_result = state.get("final_result") or state.get("last_result") or state.get("last_error") or ""
    if state.get("status") == "needs_external_action":
        required_action = state.get("required_action") or {}
        action_text = json.dumps(required_action, ensure_ascii=False, default=str) if required_action else "{}"
        final_result = (
            "Python 执行失败：检测到缺失依赖或环境依赖问题。\n"
            "该问题不能通过修改当前 run_python 参数安全解决，工具子图不会自动调用 run_command 安装依赖。\n"
            "请由主图根据用户意图、安全策略和沙箱状态决定是否执行外部动作。\n"
            f"失败原因: {state.get('failure_reason', '')}\n"
            f"建议外部动作: {action_text}\n"
            f"最后一次错误或结果:\n{state.get('last_error') or state.get('last_result') or final_result}"
        )
    elif state.get("status") not in {"success", "unknown_tool"} and state.get("retry_count", 0) >= state.get(
        "max_retries", get_max_retries(state.get("tool_name", ""))
    ):
        final_result = (
            f"工具执行失败，已达到最大重试次数 {state.get('max_retries', 0)}。\n"
            f"失败原因: {state.get('failure_reason', '')}\n"
            f"最后一次错误或结果:\n{state.get('last_error') or state.get('last_result') or final_result}"
        )
    if not final_result:
        final_result = "工具执行完成，但没有返回内容。"
    return {"final_result": final_result}


def route_after_execute(state: ToolExecutionState) -> str:
    status = state.get("status", "")
    if status in {"success", "unknown_tool", "terminal_failure", "needs_external_action"}:
        return "finalize"
    if state.get("retry_count", 0) >= state.get("max_retries", get_max_retries(state.get("tool_name", ""))):
        return "finalize"
    if status == "retryable_failure":
        return "fix"
    return "finalize"


def route_after_fix(state: ToolExecutionState) -> str:
    if state.get("status") == "retrying":
        return "execute"
    return "finalize"


def build_tool_execution_subgraph():
    workflow = StateGraph(ToolExecutionState)
    workflow.add_node("execute", execute_node)
    workflow.add_node("fix", fix_node)
    workflow.add_node("finalize", finalize_node)

    workflow.add_edge(START, "execute")
    workflow.add_conditional_edges("execute", route_after_execute, {"fix": "fix", "finalize": "finalize"})
    workflow.add_conditional_edges("fix", route_after_fix, {"execute": "execute", "finalize": "finalize"})
    workflow.add_edge("finalize", END)

    return workflow.compile()


tool_execution_subgraph = build_tool_execution_subgraph()
