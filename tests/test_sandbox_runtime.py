import os
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.tools.sandbox import DockerSandboxRuntime, ResourceLimits, add_shared_mount
from app.tools.context import set_session_id


class DockerSandboxRuntimeTests(unittest.TestCase):
    def setUp(self):
        set_session_id("unit-sandbox")

    def test_docker_runtime_lazily_starts_session_container_then_execs(self):
        missing = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="missing")
        started = subprocess.CompletedProcess(args=[], returncode=0, stdout="container-id\n", stderr="")
        executed = subprocess.CompletedProcess(args=[], returncode=0, stdout="ok\n", stderr="")

        with patch("app.tools.sandbox.subprocess.run", side_effect=[missing, started, executed]) as run_mock, patch.dict(
            os.environ,
            {
                "AGENT_SANDBOX_USER": "1000:1000",
                "AGENT_SANDBOX_WORKDIR": "/workspace/work",
            },
            clear=False,
        ):
            runtime = DockerSandboxRuntime(
                image="python:3.12-slim",
                limits=ResourceLimits(cpus="1", memory="512m", pids_limit="64", timeout_seconds=7),
            )
            result = runtime.run_command("printf ok")

        inspect_args = run_mock.call_args_list[0].args[0]
        start_args = run_mock.call_args_list[1].args[0]
        exec_args = run_mock.call_args_list[2].args[0]

        self.assertEqual(inspect_args[:4], ["docker", "inspect", "-f", "{{.State.Running}}"])
        self.assertEqual(start_args[:4], ["docker", "run", "-d", "--rm"])
        self.assertIn("--read-only", start_args)
        self.assertIn("--tmpfs", start_args)
        self.assertIn("/tmp:rw,nosuid,nodev,size=512m", start_args)
        self.assertIn("--cpus", start_args)
        self.assertIn("1", start_args)
        self.assertIn("--memory", start_args)
        self.assertIn("512m", start_args)
        self.assertIn("--pids-limit", start_args)
        self.assertIn("64", start_args)
        self.assertIn("-w", start_args)
        self.assertIn("/workspace/work", start_args)
        self.assertIn("python:3.12-slim", start_args)
        self.assertNotIn("--network", start_args)
        self.assertTrue(any(item.endswith(":/workspace/work:rw") for item in start_args))
        self.assertEqual(exec_args[:3], ["docker", "exec", "-w"])
        self.assertEqual(exec_args[-3:], ["/bin/sh", "-lc", "printf ok"])
        self.assertEqual(run_mock.call_args_list[2].kwargs["timeout"], 7)
        self.assertEqual(result.stdout, "ok")
        self.assertEqual(result.metadata["runtime"], "docker")
        self.assertEqual(result.metadata["session_id"], "unit-sandbox")

    def test_docker_runtime_reuses_running_session_container(self):
        running = subprocess.CompletedProcess(args=[], returncode=0, stdout="true\n", stderr="")
        executed = subprocess.CompletedProcess(args=[], returncode=0, stdout="ok\n", stderr="")

        with patch("app.tools.sandbox.subprocess.run", side_effect=[running, executed]) as run_mock:
            runtime = DockerSandboxRuntime(image="python:3.12-slim")
            result = runtime.run_python("print('ok')")

        calls = [call.args[0] for call in run_mock.call_args_list]
        self.assertEqual(calls[0][:4], ["docker", "inspect", "-f", "{{.State.Running}}"])
        self.assertEqual(calls[1][:3], ["docker", "exec", "-w"])
        self.assertFalse(any(call[:4] == ["docker", "run", "-d", "--rm"] for call in calls))
        self.assertEqual(calls[1][-3:], ["python", "-c", "print('ok')"])
        self.assertEqual(result.stdout, "ok")

    def test_docker_runtime_mounts_authorized_shared_dirs_readonly(self):
        missing = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="missing")
        started = subprocess.CompletedProcess(args=[], returncode=0, stdout="container-id\n", stderr="")
        executed = subprocess.CompletedProcess(args=[], returncode=0, stdout="ok\n", stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shared = root / "docs"
            shared.mkdir()
            with patch("app.tools.sandbox.subprocess.run", side_effect=[missing, started, executed]) as run_mock, patch(
                "app.runtime_paths.SESSIONS_DATA_DIR", root / ".data" / "sessions"
            ):
                add_shared_mount("docs", str(shared), session_id="unit-sandbox")
                runtime = DockerSandboxRuntime(image="python:3.12-slim")
                runtime.run_command("printf ok")

        start_args = run_mock.call_args_list[1].args[0]
        self.assertIn(f"{shared.resolve()}:/workspace/shared/docs:ro", start_args)

    def test_docker_runtime_preserves_windows_shared_mount_syntax(self):
        missing = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="missing")
        started = subprocess.CompletedProcess(args=[], returncode=0, stdout="container-id\n", stderr="")
        executed = subprocess.CompletedProcess(args=[], returncode=0, stdout="ok\n", stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            session_dir = root / ".data" / "sessions" / "unit-sandbox"
            session_dir.mkdir(parents=True)
            (session_dir / "shared_mounts.json").write_text(
                json.dumps(
                    [
                        {
                            "name": "docs",
                            "host_path": r"C:\Users\alice\Documents\docs",
                            "container_path": "/workspace/shared/docs",
                            "mode": "ro",
                            "host_os": "windows",
                        }
                    ]
                ),
                encoding="utf-8",
            )
            with patch("app.tools.sandbox.subprocess.run", side_effect=[missing, started, executed]) as run_mock, patch(
                "app.runtime_paths.SESSIONS_DATA_DIR", root / ".data" / "sessions"
            ):
                runtime = DockerSandboxRuntime(image="python:3.12-slim")
                runtime.run_command("printf ok")

        start_args = run_mock.call_args_list[1].args[0]
        self.assertIn(r"C:\Users\alice\Documents\docs:/workspace/shared/docs:ro", start_args)


if __name__ == "__main__":
    unittest.main()
