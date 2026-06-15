import os
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app.tools.sandbox as sandbox_module
from app.tools.sandbox import DEFAULT_SANDBOX_IMAGE, DockerSandboxRuntime, ResourceLimits, add_shared_mount, SandboxError, get_session_sandbox_status
from app.tools.context import set_session_id


class DockerSandboxRuntimeTests(unittest.TestCase):
    def setUp(self):
        set_session_id("unit-sandbox")
        sandbox_module._RUNNING_CONTAINER_CACHE.clear()

    def test_docker_runtime_lazily_starts_session_container_then_execs(self):
        missing = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="missing")
        started = subprocess.CompletedProcess(args=[], returncode=0, stdout="container-id\n", stderr="")
        prepared = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        executed = subprocess.CompletedProcess(args=[], returncode=0, stdout="ok\n", stderr="")

        with patch("app.tools.sandbox.subprocess.run", side_effect=[missing, started, prepared, executed]) as run_mock, patch.dict(
            os.environ,
            {
                "AGENT_SANDBOX_USER": "1000:1000",
                "AGENT_SANDBOX_WORKDIR": "/workspace/work",
                "https_proxy": "http://proxy:8080",
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
        prepare_args = run_mock.call_args_list[2].args[0]
        exec_args = run_mock.call_args_list[3].args[0]

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
        self.assertIn("-e", start_args)
        self.assertIn("https_proxy", start_args)
        self.assertNotIn("--network", start_args)
        self.assertTrue(any(item.endswith(":/workspace/work:rw") for item in start_args))
        self.assertEqual(prepare_args[:3], ["docker", "exec", "-w"])
        self.assertIn("python -m venv --system-site-packages /workspace/work/venv", prepare_args[-1])
        self.assertIn("import requests, httpx", prepare_args[-1])
        self.assertEqual(exec_args[:3], ["docker", "exec", "-w"])
        self.assertEqual(exec_args[-3:], ["/bin/sh", "-lc", ". /workspace/work/venv/bin/activate && printf ok"])
        self.assertEqual(run_mock.call_args_list[3].kwargs["timeout"], 7)
        self.assertEqual(result.stdout, "ok")
        self.assertEqual(result.metadata["runtime"], "docker")
        self.assertEqual(result.metadata["session_id"], "unit-sandbox")

    def test_docker_runtime_reuses_running_session_container(self):
        running = subprocess.CompletedProcess(args=[], returncode=0, stdout="true\n", stderr="")
        prepared = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        executed = subprocess.CompletedProcess(args=[], returncode=0, stdout="ok\n", stderr="")

        with patch("app.tools.sandbox.subprocess.run", side_effect=[running, prepared, executed]) as run_mock:
            runtime = DockerSandboxRuntime(image="python:3.12-slim")
            result = runtime.run_python("print('ok')")

        calls = [call.args[0] for call in run_mock.call_args_list]
        self.assertEqual(calls[0][:4], ["docker", "inspect", "-f", "{{.State.Running}}"])
        self.assertEqual(calls[1][:3], ["docker", "exec", "-w"])
        self.assertIn("python -m venv --system-site-packages /workspace/work/venv", calls[1][-1])
        self.assertIn("import requests, httpx", calls[1][-1])
        self.assertEqual(calls[2][:3], ["docker", "exec", "-w"])
        self.assertFalse(any(call[:4] == ["docker", "run", "-d", "--rm"] for call in calls))
        self.assertEqual(calls[2][-3:], ["/workspace/work/venv/bin/python", "-c", "print('ok')"])
        self.assertEqual(result.stdout, "ok")

    def test_docker_runtime_skips_repeated_inspect_with_running_cache(self):
        running = subprocess.CompletedProcess(args=[], returncode=0, stdout="true\n", stderr="")
        prepared = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        executed_one = subprocess.CompletedProcess(args=[], returncode=0, stdout="one\n", stderr="")
        executed_two = subprocess.CompletedProcess(args=[], returncode=0, stdout="two\n", stderr="")

        with patch("app.tools.sandbox.subprocess.run", side_effect=[running, prepared, executed_one, prepared, executed_two]) as run_mock:
            runtime = DockerSandboxRuntime(image="python:3.12-slim")
            first = runtime.run_command("printf one")
            second = runtime.run_command("printf two")

        calls = [call.args[0] for call in run_mock.call_args_list]
        inspect_calls = [call for call in calls if call[:4] == ["docker", "inspect", "-f", "{{.State.Running}}"]]
        self.assertEqual(len(inspect_calls), 1)
        self.assertEqual(first.stdout, "one")
        self.assertEqual(second.stdout, "two")

    def test_sandbox_status_does_not_start_container_when_metadata_is_absent(self):
        with tempfile.TemporaryDirectory() as tmp, patch("app.runtime_paths.SESSIONS_DATA_DIR", Path(tmp) / ".data" / "sessions"), patch(
            "app.tools.sandbox.subprocess.run"
        ) as run_mock:
            set_session_id("unit-status-only")

            status = get_session_sandbox_status()

        run_mock.assert_not_called()
        self.assertEqual(status["status"], "not_started")

    def test_docker_runtime_mounts_authorized_shared_dirs_readonly(self):
        missing = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="missing")
        started = subprocess.CompletedProcess(args=[], returncode=0, stdout="container-id\n", stderr="")
        prepared = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        executed = subprocess.CompletedProcess(args=[], returncode=0, stdout="ok\n", stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shared = root / "docs"
            shared.mkdir()
            with patch("app.tools.sandbox.subprocess.run", side_effect=[missing, started, prepared, executed]) as run_mock, patch(
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
        prepared = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
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
            with patch("app.tools.sandbox.subprocess.run", side_effect=[missing, started, prepared, executed]) as run_mock, patch(
                "app.runtime_paths.SESSIONS_DATA_DIR", root / ".data" / "sessions"
            ):
                runtime = DockerSandboxRuntime(image="python:3.12-slim")
                runtime.run_command("printf ok")

        start_args = run_mock.call_args_list[1].args[0]
        self.assertIn(r"C:\Users\alice\Documents\docs:/workspace/shared/docs:ro", start_args)

    def test_docker_cli_missing_raises_sandbox_error(self):
        # FileNotFoundError mocks missing command
        with patch("app.tools.sandbox.subprocess.run", side_effect=FileNotFoundError("No such file or directory")):
            runtime = DockerSandboxRuntime(image="python:3.12-slim")
            with self.assertRaises(SandboxError) as ctx:
                runtime.run_command("printf ok")
            self.assertIn("Docker CLI command not found", str(ctx.exception))

    def test_docker_daemon_down_raises_sandbox_error(self):
        # subprocess.run returns error during inspect
        err_res = subprocess.CompletedProcess(
            args=[],
            returncode=1,
            stdout="",
            stderr="docker: error during connect: Get http://docker/version: dial unix /var/run/docker.sock: connect: no such file or directory"
        )
        with patch("app.tools.sandbox.subprocess.run", return_value=err_res):
            runtime = DockerSandboxRuntime(image="python:3.12-slim")
            with self.assertRaises(SandboxError) as ctx:
                runtime.run_command("printf ok")
        self.assertIn("Docker daemon is not running or unavailable", str(ctx.exception))

    def test_default_runtime_uses_standard_sandbox_image(self):
        with patch.dict(os.environ, {"AGENT_SANDBOX_IMAGE": ""}, clear=False):
            runtime = DockerSandboxRuntime()
        self.assertEqual(runtime.image, DEFAULT_SANDBOX_IMAGE)

    def test_docker_runtime_passes_allowed_environment_without_metadata_secrets(self):
        missing = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="missing")
        started = subprocess.CompletedProcess(args=[], returncode=0, stdout="container-id\n", stderr="")
        prepared = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        executed = subprocess.CompletedProcess(args=[], returncode=0, stdout="ok\n", stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("app.tools.sandbox.subprocess.run", side_effect=[missing, started, prepared, executed]) as run_mock, patch(
                "app.runtime_paths.SESSIONS_DATA_DIR", root / ".data" / "sessions"
            ), patch.dict(
                os.environ,
                {
                    "MAPBOX_ACCESS_TOKEN": "mapbox-secret",
                    "AGENT_SANDBOX_ENV": "CUSTOM_API_TOKEN",
                    "CUSTOM_API_TOKEN": "custom-secret",
                },
                clear=False,
            ):
                runtime = DockerSandboxRuntime(image="python:3.12-slim")
                runtime.run_command("printf ok")

            session_metadata = root / ".data" / "sessions" / "unit-sandbox" / "sandbox.json"
            metadata_text = session_metadata.read_text(encoding="utf-8")

        start_args = run_mock.call_args_list[1].args[0]
        self.assertIn("-e", start_args)
        self.assertIn("MAPBOX_ACCESS_TOKEN=mapbox-secret", start_args)
        self.assertIn("CUSTOM_API_TOKEN=custom-secret", start_args)
        self.assertIn("environment_fingerprint", metadata_text)
        self.assertNotIn("mapbox-secret", metadata_text)
        self.assertNotIn("custom-secret", metadata_text)


if __name__ == "__main__":
    unittest.main()
