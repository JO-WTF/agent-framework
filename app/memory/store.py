import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.runtime_paths import GLOBAL_DATA_DIR, ROOT_DIR, ensure_runtime_dirs, get_session_file_path

STATIC_GUIDELINES_FILE = ROOT_DIR / "CLAUDE.md"
GLOBAL_AGENT_MEMORY_FILE = GLOBAL_DATA_DIR / "agent_memory.json"

DEFAULT_MESSAGE_WINDOW = 8
MAX_AGENT_NOTES = 100
MAX_ARCHIVE_RECORDS = 200
MAX_TOOL_RESULTS = 200
MAX_SUMMARY_CHARS = 1024
MAX_NOTE_SUMMARY_CHARS = 200


def _ensure_dirs() -> None:
    """Create data directories if they don't exist."""
    ensure_runtime_dirs()


def _read_json(path: Path, default: Any) -> Any:
    try:
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_static_guidelines() -> str:
    if not STATIC_GUIDELINES_FILE.exists():
        return ""
    return STATIC_GUIDELINES_FILE.read_text(encoding="utf-8").strip()


def load_agent_notes(limit: int = 10) -> str:
    """Load global agent notes (not session-specific)."""
    _ensure_dirs()
    notes = _read_json(GLOBAL_AGENT_MEMORY_FILE, [])
    if not notes:
        return ""
    lines = ["【Agent Auto Memory 笔记】"]
    for note in notes[:limit]:
        source = note.get("source", "agent")
        summary = note.get("summary", "(无摘要)")
        lines.append(f"- [{source}] {summary}")
    return "\n".join(lines)


def save_agent_note(note: str, source: str = "agent", tags: list[str] | str | None = None) -> str:
    """Save global agent note (not session-specific)."""
    _ensure_dirs()
    notes = _read_json(GLOBAL_AGENT_MEMORY_FILE, [])
    if isinstance(tags, str):
        tags = [tags]
    note_text = note.strip()
    summary = note_text.splitlines()[0][:MAX_NOTE_SUMMARY_CHARS]
    if any(existing.get("summary") == summary and existing.get("source") == source for existing in notes):
        return next((existing.get("id") for existing in notes if existing.get("summary") == summary and existing.get("source") == source), "")

    note_id = f"note-{len(notes) + 1:03d}"
    payload = {
        "id": note_id,
        "created_at": datetime.now().isoformat(),
        "source": source,
        "tags": tags or [],
        "summary": summary,
        "note": note_text,
    }
    notes.insert(0, payload)
    _write_json(GLOBAL_AGENT_MEMORY_FILE, notes[:MAX_AGENT_NOTES])
    return note_id


def store_tool_result(tool_name: str, raw_output: str, session_id: str | None = None, metadata: dict[str, Any] | None = None) -> str:
    """Store tool result in session-specific directory."""
    if not session_id:
        raise ValueError("session_id is required for tool result storage")

    tool_results_file = get_session_file_path(session_id, "tool_results.json")
    records = _read_json(tool_results_file, [])
    ref_id = f"tool-{len(records) + 1:04d}"
    payload = {
        "id": ref_id,
        "created_at": datetime.now().isoformat(),
        "tool_name": tool_name,
        "summary": summarize_text(raw_output, max_chars=256),
        "metadata": metadata or {},
        "content": raw_output,
    }
    records.insert(0, payload)
    _write_json(tool_results_file, records[:MAX_TOOL_RESULTS])
    return ref_id


def summarize_text(text: str, max_chars: int = MAX_SUMMARY_CHARS) -> str:
    if not text:
        return ""
    cleaned = text.strip()
    if len(cleaned) <= max_chars:
        return cleaned
    shortened = cleaned[:max_chars]
    if "\n" in shortened:
        shortened = shortened.rsplit("\n", 1)[0]
    return f"{shortened}\n...（已截断，完整内容已存档）"


def _serialize_message(message: Any) -> dict[str, Any]:
    if isinstance(message, HumanMessage):
        role = "user"
    elif isinstance(message, AIMessage):
        role = "assistant"
    elif isinstance(message, ToolMessage):
        role = "tool"
    else:
        role = getattr(message, "type", "unknown")

    return {
        "role": role,
        "content": getattr(message, "content", ""),
        "tool_calls": getattr(message, "tool_calls", None) or [],
    }


def archive_messages(messages: list[Any], session_id: str | None = None) -> str:
    """Archive messages in session-specific directory."""
    if not messages:
        return ""
    if not session_id:
        raise ValueError("session_id is required for message archival")

    archive_file = get_session_file_path(session_id, "conversation_archive.json")
    history = _read_json(archive_file, [])
    archive_id = f"archive-{len(history) + 1:04d}"
    payload = {
        "id": archive_id,
        "created_at": datetime.now().isoformat(),
        "messages": [_serialize_message(message) for message in messages],
    }
    history.insert(0, payload)
    _write_json(archive_file, history[:MAX_ARCHIVE_RECORDS])
    return archive_id


def append_session_event(session_id: str | None, event: dict[str, Any]) -> None:
    """Persist a web-console event to a session-specific JSONL log."""
    if not session_id:
        raise ValueError("session_id is required for session event logging")

    event_file = get_session_file_path(session_id, "events.jsonl")
    payload = {
        "created_at": datetime.now().isoformat(),
        **event,
    }
    with event_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(make_json_safe_for_storage(payload), ensure_ascii=False) + "\n")


def make_json_safe_for_storage(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): make_json_safe_for_storage(val) for key, val in value.items()}
    if isinstance(value, list | tuple):
        return [make_json_safe_for_storage(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (AIMessage, HumanMessage, ToolMessage)):
        return _serialize_message(value)
    return str(value)


def _build_summary_message(messages: list[Any]) -> HumanMessage:
    lines = ["【自动压缩早期对话】以下内容已存档，当前对话窗口仅保留关键摘要："]
    for message in messages[-5:]:
        role = message.__class__.__name__
        content = getattr(message, "content", "").replace("\n", " ").strip()
        if not content:
            continue
        if len(content) > 180:
            content = content[:180] + "..."
        lines.append(f"{role}: {content}")
    return HumanMessage(content="\n".join(lines))


def trim_messages(messages: list[Any], keep_recent: int = DEFAULT_MESSAGE_WINDOW, session_id: str | None = None) -> list[Any]:
    if len(messages) <= keep_recent:
        return list(messages)

    early_messages = messages[:-keep_recent]
    recent_messages = list(messages[-keep_recent:])
    preserved: list[Any] = []
    seen_ids: set[int] = set()
    pattern = re.compile(r"\b(todo|任务|关键|问题|error|失败|必须|bug|修复|阻塞|说明)\b", re.I)

    for message in early_messages:
        if id(message) in seen_ids:
            continue
        if isinstance(message, ToolMessage):
            preserved.append(message)
            seen_ids.add(id(message))
            continue
        if isinstance(message, AIMessage) and getattr(message, "tool_calls", None):
            preserved.append(message)
            seen_ids.add(id(message))
            continue
        content = getattr(message, "content", "")
        if pattern.search(content):
            preserved.append(message)
            seen_ids.add(id(message))
            continue

    omitted = [m for m in early_messages if id(m) not in seen_ids]
    if omitted:
        # Use session_id if provided, otherwise skip archival (CLI will use default session)
        if session_id:
            archive_messages(omitted, session_id=session_id)
        else:
            # For backward compatibility, try to use context session_id
            from app.tools.context import get_session_id
            current_session = get_session_id()
            if current_session:
                archive_messages(omitted, session_id=current_session)
        preserved.append(_build_summary_message(omitted))

    return preserved + recent_messages
