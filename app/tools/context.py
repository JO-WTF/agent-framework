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
