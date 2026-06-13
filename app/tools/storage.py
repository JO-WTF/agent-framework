from typing import Any

from app.memory.store import store_tool_result, summarize_text
from app.runtime_paths import get_session_file_path
from app.tools.context import ensure_session_id



class StructuredToolResult:
    """
    A mechanism for tools to return BOTH a short instructional message to the agent
    AND a large structured payload that is archived in the background.
    
    If `{{REF_ID}}` is present in `agent_message`, it will be replaced by the generated ref_id.
    """
    def __init__(self, agent_message: str, raw_output: str, metadata: dict | None = None):
        self.agent_message = agent_message
        self.raw_output = raw_output
        self.metadata = metadata

def store_tool_result_for_current_session(tool_name: str, raw_output: str, metadata: dict | None = None) -> str:

    return store_tool_result(
        tool_name,
        raw_output,
        session_id=ensure_session_id(),
        metadata=metadata,
    )


def list_tool_results_for_current_session(limit: int = 10) -> list[dict[str, Any]]:
    records = _read_current_tool_records()
    safe_limit = max(1, min(int(limit), 50))
    return [
        {
            "id": record.get("id", ""),
            "created_at": record.get("created_at", ""),
            "tool_name": record.get("tool_name", ""),
            "summary": record.get("summary", ""),
            "metadata": record.get("metadata", {}),
            "content_length": len(str(record.get("content", ""))),
        }
        for record in records[:safe_limit]
    ]


def read_tool_result_for_current_session(ref_id: str, offset: int = 0, limit: int = 8000) -> dict[str, Any]:
    cleaned_ref = str(ref_id).strip()
    if not cleaned_ref:
        raise ValueError("ref_id is required")
    safe_offset = max(0, int(offset))
    if limit is None or int(limit) <= 0:
        safe_limit = None
    else:
        safe_limit = int(limit)

    for record in _read_current_tool_records():
        if record.get("id") != cleaned_ref:
            continue
        content = str(record.get("content", ""))
        if safe_limit is None:
            chunk = content[safe_offset:]
        else:
            chunk = content[safe_offset : safe_offset + safe_limit]
        next_offset = safe_offset + len(chunk)
        return {
            "id": record.get("id", ""),
            "created_at": record.get("created_at", ""),
            "tool_name": record.get("tool_name", ""),
            "metadata": record.get("metadata", {}),
            "summary": record.get("summary", summarize_text(content, max_chars=256)),
            "offset": safe_offset,
            "limit": safe_limit,
            "content_length": len(content),
            "has_more": next_offset < len(content),
            "next_offset": next_offset if next_offset < len(content) else None,
            "content": chunk,
        }
    raise ValueError(f"tool result not found: {cleaned_ref}")


def _read_current_tool_records() -> list[dict[str, Any]]:
    session_id = ensure_session_id()
    records: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for record in _read_jsonl_records(get_session_file_path(session_id, "tool_results.jsonl")):
        record_id = str(record.get("id", ""))
        if record_id in seen_ids:
            continue
        seen_ids.add(record_id)
        records.append(record)

    for record in _read_legacy_json_records(get_session_file_path(session_id, "tool_results.json")):
        record_id = str(record.get("id", ""))
        if record_id in seen_ids:
            continue
        seen_ids.add(record_id)
        records.append(record)

    return records


def _read_jsonl_records(path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    try:
        import json

        lines = path.read_text(encoding="utf-8").splitlines()
        for line in reversed(lines):
            if not line.strip():
                continue
            record = json.loads(line)
            if isinstance(record, dict):
                records.append(record)
    except Exception:
        return []
    return records


def _read_legacy_json_records(path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        import json

        records = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    return [record for record in records if isinstance(record, dict)] if isinstance(records, list) else []
