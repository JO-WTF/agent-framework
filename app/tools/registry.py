from app.tools.command_runner import run_command
from app.tools.context import get_session_id, set_session_id
from app.tools.python_runner import run_python
from app.tools.sandbox_tools import add_shared_mount_tool, apply_sandbox_file, sandbox_status, start_sandbox, stop_sandbox
from app.tools.search import search_web
from app.tools.fetch import fetch_url
from app.tools.tool_results import list_tool_results, read_tool_result
from app.tools.skills import save_skill_sop, list_skills, delete_skill_sop, get_skill_sop
from app.tools.curl import curl


BASE_AGENT_TOOLS = [
    search_web,
    fetch_url,
    list_tool_results,
    read_tool_result,
    run_python,
    run_command,
    curl,
]

SANDBOX_CONTROL_TOOLS = [
    start_sandbox,
    sandbox_status,
    stop_sandbox,
]

APPROVAL_TOOLS = [
    add_shared_mount_tool,
    apply_sandbox_file,
]

SKILL_TOOLS = [
    save_skill_sop,
    list_skills,
    delete_skill_sop,
    get_skill_sop,
]

AGENT_TOOLS = [
    *BASE_AGENT_TOOLS,
    *SANDBOX_CONTROL_TOOLS,
    *APPROVAL_TOOLS,
    *SKILL_TOOLS,
]


SANDBOX_CONTEXT_TAGS = {"command", "python", "file_system", "security", "tool_error"}
SKILL_CONTEXT_TAGS = {"memory"}
SANDBOX_KEYWORDS = (
    "sandbox",
    "沙箱",
    "docker",
    "共享",
    "挂载",
    "写回",
    "审批",
    "workspace",
    "/workspace",
    "repo://",
    "shared://",
)
SKILL_KEYWORDS = (
    "skill",
    "skills",
    "sop",
    "技能",
    "沉淀",
    "保存经验",
    "保存流程",
    "删除技能",
    "查看技能",
)


def _dedupe_tools(tools: list) -> list:
    seen = set()
    unique = []
    for tool in tools:
        if tool.name in seen:
            continue
        seen.add(tool.name)
        unique.append(tool)
    return unique


def get_agent_tools(context_tags: list[str] | None = None, recent_text: str = "") -> list:
    """Select a conservative subset of tools to expose to the agent LLM."""
    tags = {str(tag).strip().lower() for tag in (context_tags or []) if str(tag).strip()}
    text = recent_text.lower()
    selected = list(BASE_AGENT_TOOLS)

    if tags.intersection(SANDBOX_CONTEXT_TAGS) or any(keyword in text for keyword in SANDBOX_KEYWORDS):
        selected.extend(SANDBOX_CONTROL_TOOLS)
        selected.extend(APPROVAL_TOOLS)

    if tags.intersection(SKILL_CONTEXT_TAGS) or any(keyword in text for keyword in SKILL_KEYWORDS):
        selected.extend(SKILL_TOOLS)

    return _dedupe_tools(selected)
