from pathlib import Path


APP_DIR = Path(__file__).resolve().parent
ROOT_DIR = APP_DIR.parent
CONFIG_DIR = ROOT_DIR / "config"
STATIC_DIR = APP_DIR / "web_static"
DATA_DIR = ROOT_DIR / ".data"
GLOBAL_DATA_DIR = DATA_DIR / "global"
SESSIONS_DATA_DIR = DATA_DIR / "sessions"


def ensure_runtime_dirs() -> None:
    GLOBAL_DATA_DIR.mkdir(parents=True, exist_ok=True)
    SESSIONS_DATA_DIR.mkdir(parents=True, exist_ok=True)


def get_session_dir(session_id: str | None) -> Path:
    if not session_id:
        raise ValueError("session_id is required")
    session_dir = SESSIONS_DATA_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    return session_dir


def get_session_file_path(session_id: str | None, filename: str) -> Path:
    return get_session_dir(session_id) / filename
