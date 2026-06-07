from app.memory.store import store_tool_result
from app.tools.context import ensure_session_id


def store_tool_result_for_current_session(tool_name: str, raw_output: str, metadata: dict | None = None) -> str:
    return store_tool_result(
        tool_name,
        raw_output,
        session_id=ensure_session_id(),
        metadata=metadata,
    )
