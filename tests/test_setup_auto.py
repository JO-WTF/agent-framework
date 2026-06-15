import os
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from app import setup_auto


class SetupAutoTests(unittest.TestCase):
    def test_missing_default_sandbox_image_builds_local_dockerfile(self):
        missing = subprocess.CompletedProcess(args=[], returncode=1)
        built = subprocess.CompletedProcess(args=[], returncode=0)

        with patch("app.setup_auto.run_logged", side_effect=[missing, built]) as run_mock, patch(
            "app.setup_auto.prompt_yes_no", return_value=True
        ), patch("app.setup_auto.write_progress"), patch.object(
            setup_auto, "STANDARD_SANDBOX_DOCKERFILE", Path("Dockerfile.sandbox")
        ), patch.dict(
            os.environ, {"AGENT_SANDBOX_IMAGE": "", "http_proxy": "http://proxy:8080"}, clear=True
        ):
            self.assertTrue(setup_auto.ensure_image())

        build_args = run_mock.call_args_list[1].args[0]
        self.assertEqual(build_args[:2], ["docker", "build"])
        self.assertIn("--build-arg", build_args)
        self.assertIn("http_proxy", build_args)
        self.assertIn("-f", build_args)
        self.assertIn("-t", build_args)
        self.assertIn(setup_auto.DEFAULT_IMAGE, build_args)


if __name__ == "__main__":
    unittest.main()
