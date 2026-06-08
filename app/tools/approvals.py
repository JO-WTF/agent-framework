import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from app.memory.store import summarize_text
from app.runtime_paths import get_session_file_path
from app.tools.sandbox import SandboxError, add_shared_mount, resolve_sandbox_file_writeback

MAX_APPROVALS = 100
PREVIEW_CHARS = 4000


def _approvals_path(session_id: str) -> Path:
    return get_session_file_path(session_id, "approvals.json")


def _read_approvals(session_id: str) -> list[dict[str, Any]]:
    path = _approvals_path(session_id)
    if not path.exists():
        return []
    try:
        data = path.read_text(encoding="utf-8")
        parsed = __import__("json").loads(data)
        return parsed if isinstance(parsed, list) else []
    except Exception:
        return []


def _write_approvals(session_id: str, approvals: list[dict[str, Any]]) -> None:
    import json

    path = _approvals_path(session_id)
    path.write_text(json.dumps(approvals[:MAX_APPROVALS], ensure_ascii=False, indent=2), encoding="utf-8")


def list_approvals(session_id: str, status: str | None = None) -> list[dict[str, Any]]:
    approvals = _read_approvals(session_id)
    if status:
        return [item for item in approvals if item.get("status") == status]
    return approvals


def list_pending_approvals(session_id: str | None) -> list[dict[str, Any]]:
    if not session_id:
        return []
    return [_public_approval(item) for item in list_approvals(session_id, status="pending")]


def create_file_writeback_approval(
    session_id: str,
    source_path: str,
    target_path: str,
    overwrite: bool = False,
) -> dict[str, Any]:
    resolved = resolve_sandbox_file_writeback(source_path, target_path, overwrite=overwrite, session_id=session_id)
    source = resolved["source"]
    target = resolved["target"]
    preview = _read_preview(source)
    approval = {
        "id": f"approval-{uuid.uuid4().hex[:12]}",
        "type": "sandbox_file_writeback",
        "status": "pending",
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "source_path": source_path,
        "target_path": target_path,
        "target_uri": _normalize_target_uri(target_path),
        "overwrite": overwrite,
        "source_abs": str(source),
        "target_abs": str(target),
        "source_size": str(source.stat().st_size),
        "target_exists": target.exists(),
        "preview": preview,
        "summary": summarize_text(preview, max_chars=512),
    }
    approvals = _read_approvals(session_id)
    approvals.insert(0, approval)
    _write_approvals(session_id, approvals)
    return _public_approval(approval)


def create_filesystem_access_approval(
    session_id: str,
    name: str,
    host_path: str,
    access: str = "read",
) -> dict[str, Any]:
    if access not in {"read", "write"}:
        raise SandboxError("访问授权类型必须是 'read' 或 'write'。")
    approval = {
        "id": f"approval-{uuid.uuid4().hex[:12]}",
        "type": "filesystem_access",
        "status": "pending",
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "name": name,
        "host_path": host_path,
        "access": access,
        "container_path": f"/workspace/shared/{name}",
        "summary": f"请求{'读取' if access == 'read' else '读写'}本地目录 {host_path}，容器内路径 /workspace/shared/{name}",
    }
    approvals = _read_approvals(session_id)
    approvals.insert(0, approval)
    _write_approvals(session_id, approvals)
    return _public_approval(approval)


def approve_pending_approval(session_id: str, approval_id: str) -> dict[str, Any]:
    approvals = _read_approvals(session_id)
    approval = _find_approval(approvals, approval_id)
    approval_type = approval.get("type")
    if approval_type == "sandbox_file_writeback":
        return _approve_file_writeback(session_id, approvals, approval)
    if approval_type == "filesystem_access":
        return _approve_filesystem_access(session_id, approvals, approval)
    raise SandboxError(f"不支持的审批类型: {approval_type}")


def approve_file_writeback(session_id: str, approval_id: str) -> dict[str, Any]:
    approvals = _read_approvals(session_id)
    approval = _find_approval(approvals, approval_id)
    return _approve_file_writeback(session_id, approvals, approval)


def _approve_file_writeback(session_id: str, approvals: list[dict[str, Any]], approval: dict[str, Any]) -> dict[str, Any]:
    if approval.get("status") != "pending":
        raise SandboxError(f"审批不是 pending 状态: {approval.get('status')}")
    if approval.get("type") != "sandbox_file_writeback":
        raise SandboxError(f"不支持的审批类型: {approval.get('type')}")

    resolved = resolve_sandbox_file_writeback(
        str(approval.get("source_path", "")),
        str(approval.get("target_uri") or approval.get("target_path", "")),
        overwrite=bool(approval.get("overwrite", False)),
        session_id=session_id,
    )
    source = resolved["source"]
    target = resolved["target"]
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)

    approval["status"] = "applied"
    approval["applied_at"] = datetime.now().isoformat()
    approval["updated_at"] = approval["applied_at"]
    _write_approvals(session_id, approvals)
    return _public_approval(approval)


def _approve_filesystem_access(session_id: str, approvals: list[dict[str, Any]], approval: dict[str, Any]) -> dict[str, Any]:
    if approval.get("status") != "pending":
        raise SandboxError(f"审批不是 pending 状态: {approval.get('status')}")
    access = str(approval.get("access", "read"))
    if access not in {"read", "write"}:
        raise SandboxError("不支持的访问授权类型。")

    mount = add_shared_mount(
        str(approval.get("name", "")),
        str(approval.get("host_path", "")),
        access=access,
        session_id=session_id,
    )
    approval["status"] = "approved"
    approval["mount"] = mount
    approval["approved_at"] = datetime.now().isoformat()
    approval["updated_at"] = approval["approved_at"]
    _write_approvals(session_id, approvals)

    # Sync and recreate sandbox container immediately if running
    from app.tools.sandbox import sandbox_enabled, DockerSandboxRuntime
    if sandbox_enabled():
        try:
            from app.tools.context import set_session_id
            set_session_id(session_id)
            runtime = DockerSandboxRuntime()
            runtime.ensure_container()
        except Exception as e:
            from app.logging_config import logger
            logger.warning(f"Failed to auto-recreate container during approval: {e}")

    return _public_approval(approval)


def reject_approval(session_id: str, approval_id: str) -> dict[str, Any]:
    approvals = _read_approvals(session_id)
    approval = _find_approval(approvals, approval_id)
    if approval.get("status") != "pending":
        raise SandboxError(f"审批不是 pending 状态: {approval.get('status')}")
    approval["status"] = "rejected"
    approval["rejected_at"] = datetime.now().isoformat()
    approval["updated_at"] = approval["rejected_at"]
    _write_approvals(session_id, approvals)
    return _public_approval(approval)


def _find_approval(approvals: list[dict[str, Any]], approval_id: str) -> dict[str, Any]:
    for approval in approvals:
        if approval.get("id") == approval_id:
            return approval
    raise SandboxError(f"未找到审批: {approval_id}")


def _read_preview(path: Path) -> str:
    try:
        data = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return "[binary file preview omitted]"
    if len(data) <= PREVIEW_CHARS:
        return data
    return f"{data[:PREVIEW_CHARS]}\n...（预览已截断）"


def _public_approval(approval: dict[str, Any]) -> dict[str, Any]:
    keys = {
        "id",
        "type",
        "status",
        "created_at",
        "updated_at",
        "source_path",
        "target_path",
        "target_uri",
        "overwrite",
        "source_abs",
        "target_abs",
        "source_size",
        "target_exists",
        "name",
        "host_path",
        "access",
        "container_path",
        "mount",
        "preview",
        "summary",
        "applied_at",
        "approved_at",
        "rejected_at",
    }
    return {key: approval[key] for key in keys if key in approval}


def _normalize_target_uri(target_path: str) -> str:
    if "://" in target_path:
        return target_path
    return f"repo://{target_path}"
