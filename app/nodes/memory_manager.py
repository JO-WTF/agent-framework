import asyncio
import platform
from datetime import datetime
from typing import Any

from langchain_core.messages import AIMessage, RemoveMessage, ToolMessage

from app.config import AgentState
from app.memory.proposals import (
    AGENT_CONTRACTS,
    build_task_ledger,
    derive_memory_proposals_from_state,
    route_memory_proposals,
)
from app.memory.store import archive_messages, context_size_bytes, make_json_safe_for_storage, summarize_text
from app.runtime_paths import ROOT_DIR
from app.tools.approvals import list_pending_approvals
from app.tools.sandbox import sandbox_mode, get_sandbox_world_state

MEMORY_MANAGER_KEEP_RECENT = 8
MEMORY_MANAGER_MIN_MESSAGES = 12
MEMORY_MANAGER_ARCHIVE_BYTES = 128 * 1024
MAX_WORLD_STATE_TOOL_RESULTS = 30


def _message_id(message: Any) -> str | None:
    return getattr(message, "id", None)


def _compact_tool_message(message: ToolMessage) -> dict[str, Any]:
    return {
        "tool_call_id": getattr(message, "tool_call_id", ""),
        "summary": summarize_text(str(getattr(message, "content", "")), max_chars=512),
        "updated_at": datetime.now().isoformat(),
    }


def _merge_tool_results(existing: list[dict[str, Any]], messages: list[Any]) -> list[dict[str, Any]]:
    by_id = {item.get("tool_call_id", f"idx-{idx}"): item for idx, item in enumerate(existing)}
    for message in messages:
        if isinstance(message, ToolMessage):
            compact = _compact_tool_message(message)
            by_id[compact["tool_call_id"]] = compact
    return list(by_id.values())[-MAX_WORLD_STATE_TOOL_RESULTS:]


def build_runtime_environment() -> dict[str, Any]:
    return {
        "host_os": platform.system().lower() or "unknown",
        "cwd": str(ROOT_DIR),
        "sandbox_mode": sandbox_mode(),
        "sandbox_container_paths": {
            "work": "/workspace/work",
            "shared_prefix": "/workspace/shared/<name>",
        },
        "path_protocols": ["repo://", "shared://"],
        "write_policy": "Write generated files to /workspace/work, then request approval with apply_sandbox_file before changing repo:// or shared:// targets.",
        "shared_mount_policy": "Use add_shared_mount only after the user explicitly authorizes a local directory; shared mounts are read-only in the container.",
    }


def build_world_state(state: AgentState) -> dict[str, Any]:
    """Build a compact world-state board from confirmed structured graph state."""
    previous = dict(state.get("world_state", {}) or {})
    messages = state.get("messages", [])
    task_ledger = build_task_ledger(state, previous.get("task_ledger"))
    raw_proposals = [
        *derive_memory_proposals_from_state(state),
        *(state.get("memory_proposals") or []),
    ]
    routed_memory = route_memory_proposals(
        raw_proposals,
        previous.get("memory"),
        default_source=state.get("last_node", "memory_manager") or "memory_manager",
    )

    world_state = {
        **previous,
        "task_complexity": state.get("task_complexity", previous.get("task_complexity", "unknown")),
        "context_tags": state.get("context_tags", previous.get("context_tags", ["general"])),
        "todo_list": state.get("todo_list", previous.get("todo_list", [])),
        "task_ledger": task_ledger,
        "agent_contracts": AGENT_CONTRACTS,
        "memory": routed_memory,
        "runtime_environment": build_runtime_environment(),
        "updated_at": datetime.now().isoformat(),
    }
    world_state["tool_results"] = _merge_tool_results(previous.get("tool_results", []), messages)
    sandbox = get_sandbox_world_state(state.get("session_id"))
    if sandbox is not None:
        world_state["sandbox"] = sandbox
    pending_approvals = list_pending_approvals(state.get("session_id"))
    if pending_approvals:
        world_state["pending_approvals"] = pending_approvals
    else:
        world_state.pop("pending_approvals", None)

    final_replies = [
        str(getattr(message, "content", ""))
        for message in messages[-4:]
        if isinstance(message, AIMessage) and not getattr(message, "tool_calls", None) and getattr(message, "content", "")
    ]
    if final_replies:
        world_state["last_final_reply"] = summarize_text(final_replies[-1], max_chars=512)

    return make_json_safe_for_storage(world_state)


def _has_solidified_state(world_state: dict[str, Any]) -> bool:
    return bool(world_state.get("todo_list") or world_state.get("tool_results") or world_state.get("last_final_reply"))


def _select_messages_to_archive(messages: list[Any], keep_recent: int = MEMORY_MANAGER_KEEP_RECENT) -> list[Any]:
    if len(messages) <= keep_recent:
        return []

    archive_candidates = list(messages[:-keep_recent])
    recent_messages = list(messages[-keep_recent:])

    # Avoid leaving a dangling ToolMessage at the start of retained history after removing
    # its corresponding AI tool-call message.
    while recent_messages and isinstance(recent_messages[0], ToolMessage):
        archive_candidates.append(recent_messages.pop(0))

    return [message for message in archive_candidates if _message_id(message)]


def should_archive_messages(state: AgentState, world_state: dict[str, Any]) -> bool:
    messages = state.get("messages", [])
    if not _has_solidified_state(world_state):
        return False
    if len(messages) > MEMORY_MANAGER_MIN_MESSAGES:
        return True
    return context_size_bytes(messages) > MEMORY_MANAGER_ARCHIVE_BYTES


def enqueue_archive(messages: list[Any], session_id: str | None) -> None:
    """Archive messages in the background when an event loop is available."""
    if not messages or not session_id:
        return

    async def _archive_in_background() -> None:
        await asyncio.to_thread(archive_messages, messages, session_id)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        archive_messages(messages, session_id=session_id)
        return
    loop.create_task(_archive_in_background())


async def memory_manager_node(state: AgentState) -> dict[str, Any]:
    """Persist confirmed facts into world_state and prune redundant history early."""
    if state.get("last_node") == "tools":
        return {}

    world_state = build_world_state(state)
    updates: dict[str, Any] = {"world_state": world_state}

    if not should_archive_messages(state, world_state):
        return updates

    if not state.get("session_id"):
        return updates

    messages_to_archive = _select_messages_to_archive(state.get("messages", []))
    if not messages_to_archive:
        return updates

    enqueue_archive(messages_to_archive, state.get("session_id"))
    updates["messages"] = [RemoveMessage(id=_message_id(message)) for message in messages_to_archive if _message_id(message)]
    return updates


def _route_to_selected_agent(state: AgentState) -> str:
    return "network_specialist_agent" if state.get("agent_role") == "network" else "agent"


def route_after_memory(state: AgentState) -> str:
    """Route after memory consolidation, using the node that produced the latest update."""
    last_message = state["messages"][-1]
    origin = state.get("last_node", "")

    if origin in {"agent", "network_specialist_agent"}:
        if isinstance(last_message, AIMessage) and getattr(last_message, "tool_calls", None):
            return "tools"
        return "orchestrator"

    if origin == "tools":
        return _route_to_selected_agent(state)

    if origin == "orchestrator":
        if state.get("orchestrator_next") == "evaluate" and isinstance(last_message, AIMessage):
            return "evaluate"
        return _route_to_selected_agent(state)

    if isinstance(last_message, AIMessage) and getattr(last_message, "tool_calls", None):
        return "tools"
    if isinstance(last_message, ToolMessage):
        return "orchestrator"
    return _route_to_selected_agent(state)
