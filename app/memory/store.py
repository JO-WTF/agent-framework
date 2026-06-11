import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.runtime_paths import GLOBAL_DATA_DIR, ROOT_DIR, ensure_runtime_dirs, get_session_file_path

STATIC_GUIDELINES_FILE = ROOT_DIR / "STATIC_GUIDELINES.md"
SKILLS_DIR = ROOT_DIR / "skills"
GLOBAL_AGENT_MEMORY_FILE = GLOBAL_DATA_DIR / "agent_memory.json"

DEFAULT_MESSAGE_WINDOW = 8
MAX_AGENT_NOTES = 100
MAX_ARCHIVE_RECORDS = 200
MAX_TOOL_RESULTS = 200
MAX_SUMMARY_CHARS = 1024
MAX_NOTE_SUMMARY_CHARS = 200
DEFAULT_MAX_CONTEXT_SIZE_KB = 512
MAX_CONTEXT_SIZE_KB_ENV = "MAX_CONTEXT_SIZE_KB"
DEFAULT_CONTEXT_TAG = "general"
MAX_STATIC_GUIDELINE_SECTIONS = 8
MAX_STATIC_GUIDELINE_CHARS = 6000
KNOWN_CONTEXT_TAGS = (
    "general",
    "database",
    "file_system",
    "api_call",
    "search",
    "python",
    "command",
    "tool_error",
    "memory",
    "security",
    "web",
    "network",
)



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


def normalize_context_tags(tags: list[str] | tuple[str, ...] | set[str] | str | None) -> list[str]:
    if not tags:
        return [DEFAULT_CONTEXT_TAG]
    if isinstance(tags, str):
        raw_tags = re.split(r"[,\s]+", tags)
    else:
        raw_tags = [str(tag) for tag in tags]

    normalized: list[str] = []
    for tag in raw_tags:
        cleaned = tag.strip().strip("[]").lower().replace("-", "_")
        if not cleaned or cleaned in normalized:
            continue
        normalized.append(cleaned)
    return normalized or [DEFAULT_CONTEXT_TAG]


def infer_context_tags(text: str = "", source: str = "") -> list[str]:
    haystack = f"{source}\n{text}".lower()
    tags: list[str] = []
    keyword_map = {
        "database": ("database", "sql", "db", "postgres", "mysql", "sqlite", "数据库"),
        "file_system": ("file", "path", "directory", "filesystem", "文件", "目录", "路径"),
        "api_call": ("api", "http", "request", "endpoint", "接口"),
        "search": ("search", "tavily", "联网", "搜索", "检索"),
        "python": ("python", "traceback", "run_python", "代码报错"),
        "command": ("command", "shell", "terminal", "run_command", "命令"),
        "tool_error": ("tool_error", "失败", "error", "exception", "timeout", "报错"),
        "security": ("security", "安全", "permission", "权限", "危险"),
        "web": ("web", "fastapi", "browser", "ui", "网页"),
        "network": (
            "map", "geo", "gis", "coordinate", "coordinates", "latitude", "longitude",
            "lat", "lon", "lng", "geocode", "geojson", "shapefile", "h3", "geohash",
            "logistics", "warehouse", "site", "station", "depot", "hub", "route",
            "routing", "delivery", "transport", "distance", "coverage", "facility location",
            "地图", "经纬度", "坐标", "物流", "仓库", "仓", "站点", "网点", "门店",
            "配送", "运输", "路线", "路径", "距离", "覆盖", "服务半径", "选址",
            "分拨", "干线", "支线", "末端", "调拨", "仓网", "网络拓扑",
        ),
    }
    for tag, keywords in keyword_map.items():
        if any(keyword in haystack for keyword in keywords):
            tags.append(tag)
    return normalize_context_tags(tags)


def _extract_inline_tags(text: str) -> list[str]:
    tags: list[str] = []
    for match in re.finditer(r"\[([a-zA-Z0-9_,\-\s]+)\]", text):
        tags.extend(normalize_context_tags(match.group(1)))
    return [tag for tag in normalize_context_tags(tags) if tag != DEFAULT_CONTEXT_TAG] if tags else []


def _split_tagged_guideline_sections(text: str) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    current_title = "全局规则"
    current_tags: list[str] = [DEFAULT_CONTEXT_TAG]
    current_lines: list[str] = []

    def flush() -> None:
        content = "\n".join(current_lines).strip()
        if content:
            sections.append({"title": current_title, "tags": current_tags, "content": content})

    for line in text.splitlines():
        heading_match = re.match(r"^(#{1,6})\s+(.*)$", line)
        tag_line_match = re.match(r"^\s*\[([a-zA-Z0-9_,\-\s]+)\]\s*(.*)$", line)
        if heading_match:
            flush()
            heading = heading_match.group(2).strip()
            inline_tags = _extract_inline_tags(heading)
            current_title = re.sub(r"\s*\[[^\]]+\]", "", heading).strip() or "规则"
            current_tags = inline_tags or [DEFAULT_CONTEXT_TAG]
            current_lines = [line]
        elif tag_line_match and current_lines:
            current_tags = normalize_context_tags(tag_line_match.group(1))
            remainder = tag_line_match.group(2).strip()
            if remainder:
                current_lines.append(remainder)
        else:
            current_lines.append(line)
    flush()
    return sections


def load_static_guidelines(context_tags: list[str] | str | None = None, max_sections: int = MAX_STATIC_GUIDELINE_SECTIONS) -> str:
    if not STATIC_GUIDELINES_FILE.exists():
        return ""
    selected_tags = set(normalize_context_tags(context_tags))
    raw_text = STATIC_GUIDELINES_FILE.read_text(encoding="utf-8").strip()
    if not raw_text:
        return ""

    sections = _split_tagged_guideline_sections(raw_text)
    selected_sections = [
        section
        for section in sections
        if selected_tags.intersection(section.get("tags", []))
    ]
    if not selected_sections and DEFAULT_CONTEXT_TAG in selected_tags:
        selected_sections = sections[:1]

    lines: list[str] = []
    for section in selected_sections[:max_sections]:
        tags_label = ", ".join(section.get("tags", []))
        lines.append(f"### {section.get('title', '规则')} [{tags_label}]\n{section.get('content', '').strip()}")
    result = "\n\n".join(lines).strip()
    if len(result) > MAX_STATIC_GUIDELINE_CHARS:
        result = result[:MAX_STATIC_GUIDELINE_CHARS] + "\n...（静态规则已按标签筛选并截断）"
    return result


def load_dynamic_skills(context_tags: list[str] | str | None = None) -> str:
    """Scan SKILLS_DIR, parse yaml frontmatter and load skills matching context_tags."""
    if not SKILLS_DIR.exists() or not SKILLS_DIR.is_dir():
        return ""

    selected_tags = set(normalize_context_tags(context_tags))
    if not selected_tags:
        return ""

    matched_skills = []

    for path in sorted(SKILLS_DIR.glob("*.md")):
        try:
            content = path.read_text(encoding="utf-8")
            if not content.startswith("---"):
                continue

            parts = content.split("---", 2)
            if len(parts) < 3:
                continue

            frontmatter_raw = parts[1]
            body = parts[2].strip()

            import yaml
            meta = yaml.safe_load(frontmatter_raw) or {}

            name = meta.get("name") or path.stem
            description = meta.get("description") or ""
            tags = meta.get("tags") or []
            if isinstance(tags, str):
                tags = [tags]
            normalized_skill_tags = set(normalize_context_tags(tags))

            if selected_tags.intersection(normalized_skill_tags):
                matched_skills.append({
                    "name": name,
                    "description": description,
                    "tags": list(normalized_skill_tags),
                    "body": body
                })
        except Exception as e:
            try:
                from app.logging_config import logger
                logger.warning("解析技能文件 %s 失败: %s", path.name, str(e))
            except Exception:
                pass

    if not matched_skills:
        return ""

    lines = ["【活跃技能 SOP（根据上下文自动加载）】"]
    for skill in matched_skills:
        tags_str = ", ".join(sorted(skill["tags"]))
        lines.append(f"#### {skill['name']} - {skill['description']} [标签: {tags_str}]\n{skill['body']}")

    return "\n\n".join(lines).strip()


def get_active_skill_names(context_tags: list[str] | str | None = None) -> list[str]:
    """Scan SKILLS_DIR and return names of skills matching context_tags."""
    if not SKILLS_DIR.exists() or not SKILLS_DIR.is_dir():
        return []

    selected_tags = set(normalize_context_tags(context_tags))
    if not selected_tags:
        return []

    matched_names = []
    for path in sorted(SKILLS_DIR.glob("*.md")):
        try:
            content = path.read_text(encoding="utf-8")
            if not content.startswith("---"):
                continue

            parts = content.split("---", 2)
            if len(parts) < 3:
                continue

            frontmatter_raw = parts[1]
            import yaml
            meta = yaml.safe_load(frontmatter_raw) or {}

            name = meta.get("name") or path.stem
            tags = meta.get("tags") or []
            if isinstance(tags, str):
                tags = [tags]
            normalized_skill_tags = set(normalize_context_tags(tags))

            if selected_tags.intersection(normalized_skill_tags):
                matched_names.append(name)
        except Exception:
            pass
    return matched_names


def load_agent_notes(context_tags: list[str] | str | None = None, limit: int = 5) -> str:
    """Load only agent notes matching the requested context tags."""
    _ensure_dirs()
    notes = _read_json(GLOBAL_AGENT_MEMORY_FILE, [])
    if not notes:
        return ""
    selected_tags = set(normalize_context_tags(context_tags))
    matching_notes = []
    for note in notes:
        note_tags = set(normalize_context_tags(note.get("tags") or infer_context_tags(note.get("note", ""), note.get("source", ""))))
        if selected_tags.intersection(note_tags):
            matching_notes.append((note, note_tags))
        if len(matching_notes) >= limit:
            break
    if not matching_notes:
        return ""

    lines = ["【Agent Auto Memory 笔记（按需加载）】"]
    for note, note_tags in matching_notes:
        source = note.get("source", "agent")
        summary = note.get("summary", "(无摘要)")
        tags_label = ",".join(sorted(note_tags))
        lines.append(f"- [{source} | tags: {tags_label}] {summary}")
    return "\n".join(lines)


def save_agent_note(note: str, source: str = "agent", tags: list[str] | str | None = None) -> str:
    """Save global agent note (not session-specific)."""
    _ensure_dirs()
    notes = _read_json(GLOBAL_AGENT_MEMORY_FILE, [])
    normalized_tags = normalize_context_tags(tags or infer_context_tags(note, source))
    note_text = note.strip()
    summary = note_text.splitlines()[0][:MAX_NOTE_SUMMARY_CHARS]
    if any(existing.get("summary") == summary and existing.get("source") == source for existing in notes):
        return next((existing.get("id") for existing in notes if existing.get("summary") == summary and existing.get("source") == source), "")

    note_id = f"note-{len(notes) + 1:03d}"
    payload = {
        "id": note_id,
        "created_at": datetime.now().isoformat(),
        "source": source,
        "tags": normalized_tags,
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


def get_max_context_size_kb() -> int:
    raw_value = os.getenv(MAX_CONTEXT_SIZE_KB_ENV, str(DEFAULT_MAX_CONTEXT_SIZE_KB)).strip()
    try:
        configured = int(raw_value)
    except ValueError:
        configured = DEFAULT_MAX_CONTEXT_SIZE_KB
    if configured <= 0:
        configured = DEFAULT_MAX_CONTEXT_SIZE_KB
    return configured


def get_max_context_size_bytes() -> int:
    return get_max_context_size_kb() * 1024


def _message_size_bytes(message: Any) -> int:
    return len(json.dumps(_serialize_message(message), ensure_ascii=False, default=str).encode("utf-8"))


def context_size_bytes(messages: list[Any]) -> int:
    return sum(_message_size_bytes(message) for message in messages)


def _truncate_message_content(message: Any, max_bytes: int) -> None:
    content = str(getattr(message, "content", ""))
    suffix = "\n...（已截断以满足最大上下文尺寸）"
    content_bytes = len(content.encode("utf-8"))
    overhead = _message_size_bytes(message) - content_bytes
    available = max(0, max_bytes - overhead)
    suffix_bytes = suffix.encode("utf-8")

    if available <= len(suffix_bytes):
        truncated = suffix_bytes[:available].decode("utf-8", errors="ignore")
    else:
        content_budget = available - len(suffix_bytes)
        truncated = content.encode("utf-8")[:content_budget].decode("utf-8", errors="ignore") + suffix
    message.content = truncated


def _archive_removed_messages(messages: list[Any], session_id: str | None) -> None:
    if messages and session_id:
        archive_messages(messages, session_id=session_id)


def _remove_leading_tool_messages(messages: list[Any]) -> list[Any]:
    trimmed = list(messages)
    while trimmed and isinstance(trimmed[0], ToolMessage):
        trimmed.pop(0)
    return trimmed


def _enforce_context_size(messages: list[Any], max_bytes: int, session_id: str | None) -> list[Any]:
    trimmed = list(messages)
    removed: list[Any] = []
    while len(trimmed) > 1 and context_size_bytes(trimmed) > max_bytes:
        removed.append(trimmed.pop(0))

    trimmed = _remove_leading_tool_messages(trimmed)

    if removed:
        _archive_removed_messages(removed, session_id)
        summary = _build_summary_message(removed)
        trimmed.insert(0, summary)
        while len(trimmed) > 1 and context_size_bytes(trimmed) > max_bytes:
            trimmed.pop(0)
        trimmed = _remove_leading_tool_messages(trimmed)

    if trimmed and context_size_bytes(trimmed) > max_bytes:
        _truncate_message_content(trimmed[-1], max_bytes)

    return trimmed


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
    max_context_bytes = get_max_context_size_bytes()
    if len(messages) <= keep_recent:
        return _enforce_context_size(list(messages), max_context_bytes, session_id)

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
        # Avoid preserving old summary messages to prevent duplicates/nesting in history
        if isinstance(message, HumanMessage) and content.startswith("【自动压缩早期对话】"):
            continue
        if pattern.search(content):
            preserved.append(message)
            seen_ids.add(id(message))
            continue

    omitted = [m for m in early_messages if id(m) not in seen_ids]
    if omitted:
        _archive_removed_messages(omitted, session_id)
        # Place the summary message at the start of the list to prevent breaking tool_calls -> tool adjacency
        return _enforce_context_size([_build_summary_message(omitted)] + preserved + recent_messages, max_context_bytes, session_id)

    return _enforce_context_size(preserved + recent_messages, max_context_bytes, session_id)

