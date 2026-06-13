import hashlib
import json
import os
import platform
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.runtime_paths import ROOT_DIR, get_session_dir
from app.tools.context import ensure_session_id

SHARED_MOUNTS_FILE = "shared_mounts.json"
SANDBOX_STATUS_CACHE_TTL_SECONDS = float(os.getenv("AGENT_SANDBOX_STATUS_CACHE_TTL", "2"))
DOCKER_INSPECT_TIMEOUT_SECONDS = float(os.getenv("AGENT_DOCKER_INSPECT_TIMEOUT", "2"))
_SANDBOX_WORLD_STATE_CACHE: dict[str, tuple[float, tuple[int, int], dict[str, Any]]] = {}
_RUNNING_CONTAINER_CACHE_TTL_SECONDS = float(os.getenv("AGENT_SANDBOX_RUNNING_CACHE_TTL", "2"))
_RUNNING_CONTAINER_CACHE: dict[str, float] = {}


@dataclass(frozen=True)
class ResourceLimits:
    cpus: str = "2"
    memory: str = "2g"
    pids_limit: str = "256"
    timeout_seconds: int = 30


@dataclass(frozen=True)
class SandboxResult:
    stdout: str
    stderr: str
    returncode: int
    work_dir: Path | None = None
    metadata: dict[str, str] = field(default_factory=dict)


class SandboxError(RuntimeError):
    pass


def sandbox_mode() -> str:
    return "docker"


def sandbox_enabled() -> bool:
    return True


def get_sandbox_world_state(session_id: str | None) -> dict[str, Any] | None:
    if not session_id:
        return {"mode": "docker", "status": "not_started"}

    metadata_path = get_session_dir(session_id) / "sandbox.json"
    if not metadata_path.exists():
        return {"mode": "docker", "status": "not_started"}

    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"mode": "docker", "status": "metadata_unreadable"}

    try:
        stat = metadata_path.stat()
        metadata_version = (stat.st_mtime_ns, stat.st_size)
    except OSError:
        metadata_version = (0, 0)

    now = time.monotonic()
    cached = _SANDBOX_WORLD_STATE_CACHE.get(session_id)
    if cached and cached[0] > now and cached[1] == metadata_version:
        return dict(cached[2])

    container = str(metadata.get("container", ""))
    runtime_status = str(metadata.get("status", "unknown"))
    if container and runtime_status != "stopped":
        try:
            running = inspect_container_running(container)
            if running:
                runtime_status = "running"
            else:
                runtime_status = "stopped"
        except SandboxError as e:
            runtime_status = f"unavailable: {str(e)}"

    world_state = {
        "mode": "docker",
        "status": runtime_status,
        "runtime": str(metadata.get("runtime", "docker")),
        "container": container,
        "image": str(metadata.get("image", "")),
        "work_dir": str(metadata.get("work_dir", "")),
        "shared_mounts": metadata.get("shared_mounts", []),
    }
    if SANDBOX_STATUS_CACHE_TTL_SECONDS > 0:
        _SANDBOX_WORLD_STATE_CACHE[session_id] = (
            now + SANDBOX_STATUS_CACHE_TTL_SECONDS,
            metadata_version,
            dict(world_state),
        )
    return world_state


def inspect_container_running(container_name: str) -> bool | None:
    try:
        process = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", container_name],
            capture_output=True,
            text=True,
            timeout=DOCKER_INSPECT_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as e:
        raise SandboxError("Docker CLI command not found. Please make sure Docker is installed and in your PATH.") from e
    except (OSError, subprocess.TimeoutExpired) as e:
        raise SandboxError(f"Failed to check Docker status: {e}") from e

    if process.returncode != 0:
        err_msg = process.stderr.lower()
        if "error during connect" in err_msg or "cannot connect to the docker daemon" in err_msg or "daemon" in err_msg:
            raise SandboxError(f"Docker daemon is not running or unavailable: {process.stderr.strip()}")
        # Container does not exist
        return None
    return process.stdout.strip().lower() == "true"


class DockerSandboxRuntime:
    def __init__(
        self,
        image: str | None = None,
        limits: ResourceLimits | None = None,
    ) -> None:
        self.image = image or os.getenv("AGENT_SANDBOX_IMAGE", "jupyter/scipy-notebook:latest")
        self.limits = limits or ResourceLimits(
            cpus=os.getenv("AGENT_SANDBOX_CPUS", "2"),
            memory=os.getenv("AGENT_SANDBOX_MEMORY", "2g"),
            pids_limit=os.getenv("AGENT_SANDBOX_PIDS_LIMIT", "256"),
            timeout_seconds=int(os.getenv("AGENT_SANDBOX_TIMEOUT", "30")),
        )
        self.session_id = ensure_session_id()
        self.container_name = self._container_name(self.session_id)
        self.work_dir = self._shared_work_dir(self.session_id)
        self.shared_mounts = list_shared_mounts(self.session_id)

    def run_command(self, command: str) -> SandboxResult:
        venv_activate_host = self.work_dir / "venv" / "bin" / "activate"
        if venv_activate_host.exists():
            wrapped_command = f". /workspace/work/venv/bin/activate && {command}"
        else:
            wrapped_command = command
        return self._exec(["/bin/sh", "-lc", wrapped_command])

    def run_python(self, code: str) -> SandboxResult:
        venv_python_host = self.work_dir / "venv" / "bin" / "python"
        python_exe = "/workspace/work/venv/bin/python" if venv_python_host.exists() else "python"
        return self._exec([python_exe, "-c", code])

    def _exec(self, container_command: list[str]) -> SandboxResult:
        self.ensure_container()
        args = [
            "docker",
            "exec",
            "-w",
            os.getenv("AGENT_SANDBOX_WORKDIR", "/workspace/work"),
            self.container_name,
            *container_command,
        ]

        process = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=self.limits.timeout_seconds,
        )
        self._write_metadata("running")
        return SandboxResult(
            stdout=process.stdout.strip(),
            stderr=process.stderr.strip(),
            returncode=process.returncode,
            work_dir=self.work_dir,
            metadata={
                "runtime": "docker",
                "image": self.image,
                "container": self.container_name,
                "session_id": self.session_id,
            },
        )

    def ensure_container(self) -> None:
        if self._running_cache_valid():
            return

        try:
            status = inspect_container_running(self.container_name)
        except SandboxError:
            raise
        except Exception as e:
            raise SandboxError(f"检查沙箱状态时发生未知错误: {e}") from e
        
        # Check if the mounts and configuration of the running container match current settings
        config_match = True
        if status is True:
            metadata_path = get_session_dir(self.session_id) / "sandbox.json"
            if metadata_path.exists():
                try:
                    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                    running_mounts = metadata.get("shared_mounts", [])
                    running_image = metadata.get("image", "")
                    if (running_mounts != self.shared_mounts or 
                        running_image != self.image):
                        config_match = False
                except Exception:
                    config_match = False
            else:
                config_match = False

        if status is True and config_match:
            self._write_metadata("running")
            return

        if status is True:
            try:
                from app.logging_config import logger
                logger.info("📦 \033[93m[沙箱配置发生变更，正在重新创建容器以应用新挂载...]\033[0m")
            except ImportError:
                print("Sandbox config drift detected, recreating container...")
        
        # If running but config doesn't match, or stopped: remove it first
        if (status is False) or (status is True and not config_match):
            try:
                subprocess.run(["docker", "rm", "-f", self.container_name], capture_output=True, text=True, timeout=10)
            except Exception:
                pass
        self._start_container()
        self._write_metadata("running")

    def _running_cache_key(self) -> str:
        mounts = json.dumps(self.shared_mounts, ensure_ascii=False, sort_keys=True)
        return f"{self.session_id}|{self.image}|{mounts}"

    def _running_cache_valid(self) -> bool:
        if _RUNNING_CONTAINER_CACHE_TTL_SECONDS <= 0:
            return False
        expires_at = _RUNNING_CONTAINER_CACHE.get(self._running_cache_key())
        return bool(expires_at and expires_at > time.monotonic())

    def _mark_running_cache(self) -> None:
        if _RUNNING_CONTAINER_CACHE_TTL_SECONDS <= 0:
            return
        _RUNNING_CONTAINER_CACHE[self._running_cache_key()] = time.monotonic() + _RUNNING_CONTAINER_CACHE_TTL_SECONDS

    def _clear_running_cache(self) -> None:
        prefix = f"{self.session_id}|"
        for key in list(_RUNNING_CONTAINER_CACHE):
            if key.startswith(prefix):
                _RUNNING_CONTAINER_CACHE.pop(key, None)

    def status(self) -> dict[str, Any]:
        metadata = get_sandbox_world_state(self.session_id)
        return metadata or {"mode": "docker", "status": "disabled"}

    def stop(self) -> dict[str, str]:
        subprocess.run(["docker", "stop", self.container_name], capture_output=True, text=True, timeout=15)
        self._clear_running_cache()
        self._write_metadata("stopped")
        return self.status()

    def _start_container(self) -> None:
        args = [
            "docker",
            "run",
            "-d",
            "--rm",
            "--name",
            self.container_name,
            "--label",
            "agent-framework.sandbox=true",
            "--label",
            f"agent-framework.session={self.session_id}",
            "--user",
            os.getenv("AGENT_SANDBOX_USER", "1000:1000"),
            "--cpus",
            self.limits.cpus,
            "--memory",
            self.limits.memory,
            "--pids-limit",
            self.limits.pids_limit,
            "--read-only",
            "--tmpfs",
            "/tmp:rw,nosuid,nodev,size=512m",
            "--tmpfs",
            "/workspace/shared:rw,nosuid,nodev,size=1m",
        ]
        args.extend([
            "-v",
            f"{self.work_dir}:/workspace/work:rw",
            *self._shared_mount_args(),
            "-w",
            os.getenv("AGENT_SANDBOX_WORKDIR", "/workspace/work"),
            self.image,
            "/bin/sh",
            "-lc",
            "trap 'exit 0' TERM; while true; do sleep 3600; done",
        ])

        try:
            res = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=self.limits.timeout_seconds,
            )
        except FileNotFoundError as e:
            raise SandboxError("Docker CLI command not found. Please make sure Docker is installed and in your PATH.") from e
        except (OSError, subprocess.TimeoutExpired) as e:
            raise SandboxError(f"Failed to execute Docker start command: {e}") from e

        if res.returncode != 0:
            raise SandboxError(f"Failed to start Docker sandbox container (code {res.returncode}): {res.stderr.strip()}")

    def _write_metadata(self, status: str) -> None:
        metadata_path = get_session_dir(self.session_id) / "sandbox.json"
        metadata = {
            "runtime": "docker",
            "status": status,
            "container": self.container_name,
            "image": self.image,
            "work_dir": str(self.work_dir),
            "shared_mounts": self.shared_mounts,
        }
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        if status == "running":
            self._mark_running_cache()
        else:
            self._clear_running_cache()

    @staticmethod
    def _container_name(session_id: str) -> str:
        digest = hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:16]
        return f"agent-sandbox-{digest}"

    @staticmethod
    def _shared_work_dir(session_id: str) -> Path:
        base_dir = get_session_dir(session_id) / "sandbox_work"
        path = base_dir / "shared"
        path.mkdir(parents=True, exist_ok=True)
        path.chmod(0o777)
        return path

    def _shared_mount_args(self) -> list[str]:
        args: list[str] = []
        for mount in self.shared_mounts:
            mode = mount.get("mode", "ro")
            args.extend(["-v", f"{mount['host_path']}:{mount['container_path']}:{mode}"])
        return args


def shared_mounts_path(session_id: str) -> Path:
    return get_session_dir(session_id) / SHARED_MOUNTS_FILE


def list_shared_mounts(session_id: str | None = None) -> list[dict[str, str]]:
    resolved_session_id = session_id or ensure_session_id()
    path = shared_mounts_path(resolved_session_id)
    if not path.exists():
        return []
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(parsed, list):
        return []
    return [mount for mount in parsed if _is_valid_shared_mount_record(mount)]


def add_shared_mount(name: str, host_path: str, access: str = "read", session_id: str | None = None) -> dict[str, str]:
    resolved_session_id = session_id or ensure_session_id()
    normalized_name = _validate_shared_name(name)
    host = Path(host_path).expanduser().resolve()
    if not host.exists() or not host.is_dir():
        raise SandboxError(f"共享目录不存在或不是目录: {host_path}")
    if _is_sensitive_host_path(host):
        raise SandboxError("共享目录命中敏感路径规则，已拒绝。")

    mode = "rw" if access == "write" else "ro"
    mounts = [mount for mount in list_shared_mounts(resolved_session_id) if mount["name"] != normalized_name]
    record = {
        "name": normalized_name,
        "host_path": str(host),
        "container_path": f"/workspace/shared/{normalized_name}",
        "mode": mode,
        "host_os": _host_os_for_path(host),
    }
    mounts.append(record)
    shared_mounts_path(resolved_session_id).write_text(json.dumps(mounts, ensure_ascii=False, indent=2), encoding="utf-8")
    return record


def _is_valid_shared_mount_record(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    required = ("name", "host_path", "container_path", "mode")
    if any(not isinstance(value.get(key), str) for key in required):
        return False
    return value.get("mode") in {"ro", "rw"} and value.get("container_path", "").startswith("/workspace/shared/")


def _validate_shared_name(name: str) -> str:
    cleaned = name.strip()
    if not cleaned or not cleaned.replace("_", "-").replace("-", "").isalnum():
        raise SandboxError("共享目录名称只能包含字母、数字、短横线和下划线。")
    return cleaned


def _is_sensitive_host_path(path: Path) -> bool:
    parts = [part.lower() for part in path.parts]
    sensitive_parts = {
        ".ssh",
        ".aws",
        ".azure",
        ".kube",
        ".docker",
        "appdata",
        "windows",
        "system32",
        "program files",
        "program files (x86)",
        "programdata",
        "library",
    }
    lower_name = path.name.lower()
    if lower_name in {".env"} or any(part in sensitive_parts for part in parts):
        return True
    if _is_windows_drive_root(path):
        return True
    return False


def _host_os_for_path(path: Path) -> str:
    if platform.system().lower() == "windows":
        return "windows"
    raw = str(path)
    if len(raw) >= 3 and raw[1:3] in {":\\", ":/"}:
        return "windows"
    return platform.system().lower() or "unknown"


def _is_windows_drive_root(path: Path) -> bool:
    raw = str(path)
    return len(raw) == 3 and raw[1:3] in {":\\", ":/"}


def start_session_sandbox() -> dict[str, Any]:
    runtime = DockerSandboxRuntime()
    runtime.ensure_container()
    return runtime.status()


def stop_session_sandbox() -> dict[str, Any]:
    return DockerSandboxRuntime().stop()


def get_session_sandbox_status() -> dict[str, Any]:
    runtime = DockerSandboxRuntime()
    return runtime.status()


def apply_sandbox_file_to_workspace(
    source_path: str,
    target_path: str,
    overwrite: bool = False,
    session_id: str | None = None,
) -> dict[str, str]:
    resolved = resolve_sandbox_file_writeback(source_path, target_path, overwrite=overwrite, session_id=session_id)
    source = resolved["source"]
    target = resolved["target"]
    was_existing = target.exists()
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    return {
        "source": str(source),
        "target": str(target),
        "status": "applied",
        "overwritten": str(was_existing).lower(),
    }


def resolve_sandbox_file_writeback(
    source_path: str,
    target_path: str,
    overwrite: bool = False,
    session_id: str | None = None,
) -> dict[str, Path]:
    resolved_session_id = session_id or ensure_session_id()
    work_dir = DockerSandboxRuntime._shared_work_dir(resolved_session_id)
    source = _resolve_child(work_dir, source_path)
    target = _resolve_writeback_target(target_path, resolved_session_id)

    if not source.exists():
        raise SandboxError(f"沙箱文件不存在: {source_path}")
    if not source.is_file():
        raise SandboxError("第一阶段写回只支持单个文件。")
    if target.exists() and not overwrite:
        raise SandboxError(f"目标文件已存在，若确认覆盖请设置 overwrite=true: {target_path}")
    return {"source": source, "target": target}


def _resolve_writeback_target(target_uri: str, session_id: str) -> Path:
    if "://" not in target_uri:
        return _resolve_workspace_target(target_uri)
    scheme, rest = target_uri.split("://", 1)
    if scheme == "repo":
        return _resolve_workspace_target(rest)
    if scheme == "shared":
        return _resolve_shared_target(rest, session_id)
    raise SandboxError("target_path 只支持 repo:// 或 shared:// URI。")


def _resolve_shared_target(shared_uri_path: str, session_id: str) -> Path:
    parts = Path(shared_uri_path).parts
    if len(parts) < 2:
        raise SandboxError("shared:// 目标必须包含共享名称和相对路径。")
    name = _validate_shared_name(parts[0])
    relative = Path(*parts[1:])
    if relative.is_absolute():
        raise SandboxError("shared:// 目标路径必须是相对路径。")

    mount = next((item for item in list_shared_mounts(session_id) if item["name"] == name), None)
    if not mount:
        raise SandboxError(f"未授权的共享目录: {name}")
    return _resolve_child(Path(mount["host_path"]), str(relative))


def _resolve_child(root: Path, relative_path: str) -> Path:
    if not relative_path or Path(relative_path).is_absolute():
        raise SandboxError("路径必须是非空相对路径。")
    path = (root / relative_path).resolve()
    if root.resolve() not in path.parents and path != root.resolve():
        raise SandboxError("路径不能越过允许的根目录。")
    return path


def _resolve_workspace_target(relative_path: str) -> Path:
    if not relative_path or Path(relative_path).is_absolute():
        raise SandboxError("目标路径必须是仓库内的相对路径。")
    parts = Path(relative_path).parts
    blocked = {".git", ".data", ".env"}
    if any(part in blocked for part in parts):
        raise SandboxError("目标路径包含受保护目录或文件。")
    target = (ROOT_DIR / relative_path).resolve()
    if ROOT_DIR.resolve() not in target.parents and target != ROOT_DIR.resolve():
        raise SandboxError("目标路径不能越过仓库根目录。")
    return target


def run_sandboxed_command(command: str) -> SandboxResult:
    return DockerSandboxRuntime().run_command(command)


def run_sandboxed_python(code: str) -> SandboxResult:
    return DockerSandboxRuntime().run_python(code)
