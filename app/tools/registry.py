from app.tools.command_runner import run_command
from app.tools.context import get_session_id, set_session_id
from app.tools.python_runner import run_python
from app.tools.sandbox_tools import add_shared_mount_tool, apply_sandbox_file, sandbox_status, start_sandbox, stop_sandbox
from app.tools.search import search_web
from app.tools.tool_results import list_tool_results, read_tool_result
from app.tools.skills import save_skill_sop, list_skills, delete_skill_sop, get_skill_sop
from app.tools.curl import curl


AGENT_TOOLS = [
    search_web,
    start_sandbox,
    sandbox_status,
    stop_sandbox,
    add_shared_mount_tool,
    apply_sandbox_file,
    list_tool_results,
    read_tool_result,
    run_python,
    run_command,
    save_skill_sop,
    list_skills,
    delete_skill_sop,
    get_skill_sop,
    curl,
]
