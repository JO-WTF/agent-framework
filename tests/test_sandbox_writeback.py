import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.tools.context import set_session_id
from app.tools.sandbox import SandboxError, apply_sandbox_file_to_workspace


class SandboxWritebackTests(unittest.TestCase):
    def setUp(self):
        set_session_id("unit-writeback")

    def test_apply_sandbox_file_writes_single_file_to_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            work_dir = root / ".data" / "sessions" / "unit-writeback" / "sandbox_work" / "shared"
            work_dir.mkdir(parents=True)
            (work_dir / "result.txt").write_text("hello", encoding="utf-8")

            with patch("app.tools.sandbox.ROOT_DIR", root), patch("app.tools.sandbox.get_session_dir") as get_session_dir:
                get_session_dir.return_value = root / ".data" / "sessions" / "unit-writeback"
                result = apply_sandbox_file_to_workspace("result.txt", "out/result.txt")

            self.assertEqual((root / "out" / "result.txt").read_text(encoding="utf-8"), "hello")
            self.assertEqual(result["status"], "applied")
            self.assertEqual(result["overwritten"], "false")

    def test_apply_sandbox_file_rejects_path_traversal_and_protected_targets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            work_dir = root / ".data" / "sessions" / "unit-writeback" / "sandbox_work" / "shared"
            work_dir.mkdir(parents=True)
            (work_dir / "result.txt").write_text("hello", encoding="utf-8")

            with patch("app.tools.sandbox.ROOT_DIR", root), patch("app.tools.sandbox.get_session_dir") as get_session_dir:
                get_session_dir.return_value = root / ".data" / "sessions" / "unit-writeback"
                with self.assertRaises(SandboxError):
                    apply_sandbox_file_to_workspace("../result.txt", "out/result.txt")
                with self.assertRaises(SandboxError):
                    apply_sandbox_file_to_workspace("result.txt", ".git/config")
                with self.assertRaises(SandboxError):
                    apply_sandbox_file_to_workspace("result.txt", "../outside.txt")


if __name__ == "__main__":
    unittest.main()
