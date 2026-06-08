from typing import Any

from contextvars import ContextVar


_session_id: ContextVar[str | None] = ContextVar("_session_id", default=None)


def set_session_id(session_id: str | None) -> None:
    _session_id.set(session_id)


def get_session_id() -> str | None:
    return _session_id.get()


def ensure_session_id() -> str:
    session_id = get_session_id()
    if session_id:
        return session_id
    set_session_id("cli")
    return "cli"


def get_session_id_from_config_or_context(config: Any = None) -> str:
    session_id = None
    if config:
        if isinstance(config, dict):
            session_id = config.get("configurable", {}).get("session_id")
        else:
            session_id = getattr(config, "configurable", {}).get("session_id", None)
    
    if session_id:
        set_session_id(session_id)
        return session_id
        
    return ensure_session_id()

