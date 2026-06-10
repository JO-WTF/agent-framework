import os
import platform
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOGS_DIR = PROJECT_ROOT / "logs"
STEPS_DIR = LOGS_DIR / "setup-steps"
PROGRESS_LOG = LOGS_DIR / "setup.log"
DEFAULT_IMAGE = "jupyter/scipy-notebook:latest"
DEFAULT_DOCKER_WAIT_SECONDS = 180


def main() -> int:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    STEPS_DIR.mkdir(parents=True, exist_ok=True)
    write_header()

    print("Agent Framework setup")
    print("---------------------")

    platform_info = detect_platform()
    print(f"Platform: {platform_info['platform']}{' (WSL)' if platform_info['is_wsl'] else ''}")

    if not ensure_docker(platform_info):
        return 1
    if not ensure_image():
        return 1

    write_complete()
    print("Setup complete.")
    return 0


def detect_platform() -> dict[str, object]:
    system = platform.system().lower()
    is_wsl = False
    if system == "linux":
        try:
            version = Path("/proc/version").read_text(encoding="utf-8", errors="ignore").lower()
            is_wsl = "microsoft" in version or "wsl" in version
        except OSError:
            is_wsl = False
    return {"platform": system or "unknown", "is_wsl": is_wsl}


def ensure_docker(platform_info: dict[str, object]) -> bool:
    start = time.time()
    raw_log = STEPS_DIR / "02-docker.log"
    docker_path = shutil.which("docker")
    fields = {
        "platform": str(platform_info["platform"]),
        "is_wsl": str(platform_info["is_wsl"]).lower(),
        "docker_cli": docker_path or "not_found",
    }

    if not docker_path:
        raw_log.write_text("docker CLI not found\n", encoding="utf-8")
        write_progress("docker", "missing", start, fields | {"raw": relative(raw_log)})
        if should_install_docker(platform_info):
            if not run_install_docker():
                return False
            docker_path = shutil.which("docker")
            if not docker_path:
                print("Docker install finished, but docker is still not on PATH. Restart your shell and run again.")
                return False
            fields["docker_cli"] = docker_path
            if not wait_for_docker_daemon(platform_info):
                write_progress("docker", "daemon_start_timeout", start, fields | {"raw": relative(raw_log)})
                print("Docker Desktop was installed, but the Docker daemon did not become ready in time.")
                print_docker_instructions(platform_info)
                return False
        else:
            print_docker_instructions(platform_info)
            return False

    check = run_logged(["docker", "version"], raw_log)
    if check.returncode != 0:
        if try_start_docker_daemon(platform_info) and wait_for_docker_daemon(platform_info):
            check = run_logged(["docker", "version"], raw_log, append=True)
        if check.returncode != 0:
            write_progress("docker", "daemon_unavailable", start, fields | {"raw": relative(raw_log)})
            print("Docker CLI is installed, but the Docker daemon is not available.")
            print_docker_instructions(platform_info)
            return False

    write_progress("docker", "success", start, fields | {"raw": relative(raw_log)})
    print("Docker is ready.")
    return True


def try_start_docker_daemon(platform_info: dict[str, object]) -> bool:
    system = platform_info["platform"]
    if platform_info["is_wsl"]:
        return False
    if system == "darwin":
        return subprocess.run(["open", "-a", "Docker"], capture_output=True).returncode == 0
    if system == "windows":
        candidates = [
            Path(os.getenv("ProgramFiles", "C:/Program Files")) / "Docker" / "Docker" / "Docker Desktop.exe",
            Path(os.getenv("LOCALAPPDATA", "")) / "Docker" / "Docker Desktop.exe",
        ]
        for candidate in candidates:
            if candidate.exists():
                return subprocess.run([str(candidate)], capture_output=True).returncode == 0
        return False
    if system == "linux":
        if shutil.which("systemctl"):
            command = ["systemctl", "start", "docker"]
            if os.geteuid() != 0 and shutil.which("sudo"):
                command.insert(0, "sudo")
            return subprocess.run(command, capture_output=True).returncode == 0
        if shutil.which("service"):
            command = ["service", "docker", "start"]
            if os.geteuid() != 0 and shutil.which("sudo"):
                command.insert(0, "sudo")
            return subprocess.run(command, capture_output=True).returncode == 0
    return False


def wait_for_docker_daemon(platform_info: dict[str, object]) -> bool:
    timeout = int(os.getenv("AGENT_DOCKER_START_TIMEOUT", str(DEFAULT_DOCKER_WAIT_SECONDS)))
    deadline = time.time() + timeout
    raw_log = STEPS_DIR / "02-docker-start.log"

    if platform_info["platform"] == "darwin":
        subprocess.run(["open", "-a", "Docker"], capture_output=True)

    print(f"Waiting up to {timeout}s for Docker daemon to start...")
    attempt = 0
    while time.time() < deadline:
        attempt += 1
        result = run_logged(["docker", "version"], raw_log, append=attempt > 1)
        if result.returncode == 0:
            write_progress("docker-start", "success", deadline - timeout, {"raw": relative(raw_log)})
            return True
        time.sleep(5)

    write_progress("docker-start", "timeout", deadline - timeout, {"raw": relative(raw_log)})
    return False


def ensure_image() -> bool:
    image = os.getenv("AGENT_SANDBOX_IMAGE", DEFAULT_IMAGE)
    start = time.time()
    raw_log = STEPS_DIR / "03-image.log"
    inspect = run_logged(["docker", "image", "inspect", image], raw_log)
    if inspect.returncode == 0:
        write_progress("image", "success", start, {"image": image, "raw": relative(raw_log)})
        print(f"Sandbox image ready: {image}")
        return True

    if not prompt_yes_no(f"Sandbox image {image} is missing. Pull it now?", default=True):
        write_progress("image", "missing", start, {"image": image, "raw": relative(raw_log)})
        return False

    pull = run_logged(["docker", "pull", image], raw_log, append=True)
    status = "success" if pull.returncode == 0 else "failed"
    write_progress("image", status, start, {"image": image, "raw": relative(raw_log)})
    if pull.returncode != 0:
        print(f"Failed to pull {image}. See {relative(raw_log)}")
        return False
    print(f"Sandbox image ready: {image}")
    return True


def should_install_docker(platform_info: dict[str, object]) -> bool:
    if platform_info["is_wsl"]:
        return False
    system = platform_info["platform"]
    if system not in {"darwin", "linux", "windows"}:
        return False
    return prompt_yes_no("Docker is not installed. Install it now?", default=True)


def run_install_docker() -> bool:
    system = platform.system().lower()
    if system == "windows":
        script = PROJECT_ROOT / "scripts" / "install-docker.ps1"
        shell = shutil.which("pwsh") or shutil.which("powershell") or "powershell"
        command = [shell, "-ExecutionPolicy", "Bypass", "-File", str(script)]
        raw_log = STEPS_DIR / "02-install-docker.log"
        start = time.time()
        result = run_logged(command, raw_log)
        status = "success" if result.returncode == 0 else "failed"
        write_progress("install-docker", status, start, {"raw": relative(raw_log)})
        if result.returncode != 0:
            print(f"Docker install failed. See {relative(raw_log)}")
            return False
        return True
    elif system == "darwin":
        return run_install_docker_darwin()
    else:
        # Linux
        script = PROJECT_ROOT / "scripts" / "install-docker.sh"
        command = ["bash", str(script)]
        raw_log = STEPS_DIR / "02-install-docker.log"
        start = time.time()
        result = run_logged(command, raw_log)
        status = "success" if result.returncode == 0 else "failed"
        write_progress("install-docker", status, start, {"raw": relative(raw_log)})
        if result.returncode != 0:
            print(f"Docker install failed. See {relative(raw_log)}")
            return False
        return True


def run_install_docker_darwin() -> bool:
    # Helper function to perform the official DMG installation
    def install_via_official_dmg() -> bool:
        print("Installing Docker Desktop using the official DMG installer...")
        machine = platform.machine()
        if machine == "arm64":
            dmg_url = "https://desktop.docker.com/mac/main/arm64/Docker.dmg"
        else:
            dmg_url = "https://desktop.docker.com/mac/main/amd64/Docker.dmg"

        dmg_path = Path("/tmp/Docker.dmg")
        start = time.time()
        print(f"Downloading Docker DMG from {dmg_url}...")
        # Use curl -fL --retry and -C - to handle transient network failures and resume downloads.
        download_res = subprocess.run(
            ["curl", "-fL", "--retry", "5", "--retry-delay", "2", "-C", "-", dmg_url, "-o", str(dmg_path)]
        )
        if download_res.returncode != 0:
            print("Failed to download Docker DMG. You can run setup again to resume the download.")
            write_progress("install-docker", "failed", start, {"method": "official", "reason": "download_failed"})
            return False

        print("Mounting Docker DMG...")
        mount_res = subprocess.run(["hdiutil", "attach", "-nobrowse", "-readonly", str(dmg_path)])
        if mount_res.returncode != 0:
            print("Failed to mount Docker DMG. The file might be corrupted. Removing it so next attempt starts fresh.")
            if dmg_path.exists():
                dmg_path.unlink()
            write_progress("install-docker", "failed", start, {"method": "official", "reason": "mount_failed"})
            return False

        print("Running official installer (this will request sudo privileges for installation)...")
        username = os.getenv("USER") or os.getenv("USERNAME") or ""
        install_command = [
            "sudo",
            "/Volumes/Docker/Docker.app/Contents/MacOS/install",
            "--accept-license",
        ]
        if username:
            install_command.append(f"--user={username}")
        install_res = subprocess.run(install_command)

        print("Detaching Docker DMG...")
        subprocess.run(["hdiutil", "detach", "/Volumes/Docker"], capture_output=True)

        if dmg_path.exists():
            dmg_path.unlink()

        if install_res.returncode != 0:
            print("Docker Desktop installation failed.")
            write_progress("install-docker", "failed", start, {"method": "official", "reason": "installer_failed"})
            return False

        write_progress("install-docker", "success", start, {"method": "official"})
        subprocess.run(["open", "-a", "Docker"], capture_output=True)
        print("Docker Desktop installed and requested to start.")
        return True

    # 1. Find brew
    brew_bin = shutil.which("brew")
    if not brew_bin:
        for path in ["/opt/homebrew/bin/brew", "/usr/local/bin/brew"]:
            if os.path.exists(path):
                brew_bin = path
                break

    # 2. If brew is found, use it to install Docker
    if brew_bin:
        print("Homebrew detected. Installing Docker Desktop via Homebrew Cask...")
        raw_log = STEPS_DIR / "02-install-docker.log"
        start = time.time()
        result = run_logged([brew_bin, "install", "--cask", "docker"], raw_log)
        if result.returncode == 0:
            write_progress("install-docker", "success", start, {"method": "brew", "raw": relative(raw_log)})
            subprocess.run(["open", "-a", "Docker"], capture_output=True)
            print("Docker Desktop install requested.")
            return True
        else:
            print(f"Docker install via Homebrew failed. See {relative(raw_log)}")
            if prompt_yes_no("Do you want to try downloading and installing Docker via the official DMG installer instead?", default=True):
                return install_via_official_dmg()
            write_progress("install-docker", "failed", start, {"method": "brew", "raw": relative(raw_log)})
            return False

    # 3. If brew is not found, ask if they want to install brew
    if prompt_yes_no("Homebrew is not installed. Do you want to install Homebrew and use it to install Docker? (If No, we will install Docker using the official DMG installer)", default=True):
        print("Installing Homebrew...")
        brew_installer_cmd = '/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
        start = time.time()
        result = subprocess.run(brew_installer_cmd, shell=True)
        if result.returncode != 0:
            print("Homebrew installation failed.")
            write_progress("install-brew", "failed", start, {})
            if prompt_yes_no("Do you want to try downloading and installing Docker via the official DMG installer instead?", default=True):
                return install_via_official_dmg()
            return False
        write_progress("install-brew", "success", start, {})

        # Find the new brew binary
        brew_bin = shutil.which("brew")
        if not brew_bin:
            for path in ["/opt/homebrew/bin/brew", "/usr/local/bin/brew"]:
                if os.path.exists(path):
                    brew_bin = path
                    break
        if not brew_bin:
            print("Homebrew was installed but the brew binary could not be found in standard locations.")
            if prompt_yes_no("Do you want to try downloading and installing Docker via the official DMG installer instead?", default=True):
                return install_via_official_dmg()
            return False

        print("Installing Docker Desktop via Homebrew Cask...")
        raw_log = STEPS_DIR / "02-install-docker.log"
        start = time.time()
        result = run_logged([brew_bin, "install", "--cask", "docker"], raw_log)
        if result.returncode == 0:
            write_progress("install-docker", "success", start, {"method": "brew", "raw": relative(raw_log)})
            subprocess.run(["open", "-a", "Docker"], capture_output=True)
            print("Docker Desktop install requested.")
            return True
        else:
            print(f"Docker install via Homebrew failed. See {relative(raw_log)}")
            if prompt_yes_no("Do you want to try downloading and installing Docker via the official DMG installer instead?", default=True):
                return install_via_official_dmg()
            write_progress("install-docker", "failed", start, {"method": "brew", "raw": relative(raw_log)})
            return False

    # 4. If they said no to Homebrew, use official DMG installer
    return install_via_official_dmg()


def run_logged(command: list[str], raw_log: Path, append: bool = False) -> subprocess.CompletedProcess[str]:
    mode = "a" if append else "w"
    raw_log.parent.mkdir(parents=True, exist_ok=True)
    with raw_log.open(mode, encoding="utf-8") as handle:
        handle.write(f"$ {' '.join(command)}\n")
        handle.flush()
        process = subprocess.run(command, cwd=PROJECT_ROOT, text=True, stdout=handle, stderr=subprocess.STDOUT)
        handle.write(f"\nEXIT_CODE: {process.returncode}\n")
    return process


def prompt_yes_no(question: str, default: bool) -> bool:
    assume = os.getenv("AGENT_SETUP_ASSUME_YES", "").strip().lower()
    if assume in {"1", "true", "yes", "y"}:
        print(f"{question} -> yes (AGENT_SETUP_ASSUME_YES)")
        return True
    if assume in {"0", "false", "no", "n"}:
        print(f"{question} -> no (AGENT_SETUP_ASSUME_YES)")
        return False
    if not sys.stdin.isatty():
        print(f"{question} {'[Y/n]' if default else '[y/N]'}")
        print(f"Non-interactive terminal; using default answer: {'yes' if default else 'no'}.")
        return default
    suffix = "[Y/n]" if default else "[y/N]"
    answer = input(f"{question} {suffix} ").strip().lower()
    if not answer:
        return default
    return answer in {"y", "yes"}


def print_docker_instructions(platform_info: dict[str, object]) -> None:
    system = platform_info["platform"]
    if platform_info["is_wsl"]:
        print("WSL detected. Install Docker Desktop on Windows, enable WSL integration for this distro, then run again.")
        return
    if system == "darwin":
        print("macOS: install Docker Desktop, or run: brew install --cask docker && open -a Docker")
    elif system == "linux":
        print("Linux: install Docker Engine and start the daemon. See https://docs.docker.com/engine/install/")
    elif system == "windows":
        print("Windows: install Docker Desktop, use Linux containers, then run run_web.ps1 again.")
    else:
        print("Install Docker for your platform, then run setup again.")


def write_header() -> None:
    PROGRESS_LOG.write_text(
        "\n".join(
            [
                f"## {utc_now()} · setup:auto started",
                f" invocation: python -m app.setup_auto",
                f" user: {os.getenv('USER') or os.getenv('USERNAME') or 'unknown'}",
                f" cwd: {PROJECT_ROOT}",
                "",
            ]
        ),
        encoding="utf-8",
    )


def write_progress(step: str, status: str, start: float, fields: dict[str, object]) -> None:
    duration = 0 if start == 0 else int(time.time() - start)
    with PROGRESS_LOG.open("a", encoding="utf-8") as handle:
        handle.write(f"=== [{utc_now()}] {step} [{duration}s] -> {status} ===\n")
        for key, value in fields.items():
            handle.write(f" {key}: {value}\n")
        handle.write("\n")


def write_complete() -> None:
    with PROGRESS_LOG.open("a", encoding="utf-8") as handle:
        handle.write(f"## {utc_now()} · completed\n")


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def relative(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    raise SystemExit(main())
