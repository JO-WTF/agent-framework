import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.nodes.memory_manager import build_world_state
from app.tools.approvals import (
    approve_pending_approval,
    create_file_writeback_approval,
    create_filesystem_access_approval,
    reject_approval,
)
from app.tools.sandbox import SandboxError, add_shared_mount, list_shared_mounts


class ApprovalTests(unittest.TestCase):
    def test_file_writeback_requires_approval_before_copying(self):
        session_id = "unit-approval"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            session_dir = root / ".data" / "sessions" / session_id
            work_dir = session_dir / "sandbox_work" / "shared"
            work_dir.mkdir(parents=True)
            (work_dir / "result.txt").write_text("hello", encoding="utf-8")

            with patch("app.tools.sandbox.ROOT_DIR", root), patch("app.runtime_paths.SESSIONS_DATA_DIR", root / ".data" / "sessions"):
                approval = create_file_writeback_approval(session_id, "result.txt", "out/result.txt")
                self.assertEqual(approval["status"], "pending")
                self.assertFalse((root / "out" / "result.txt").exists())

                world_state = build_world_state(
                    {
                        "messages": [],
                        "revision_count": 0,
                        "eval_status": "",
                        "session_id": session_id,
                        "task_complexity": "simple",
                        "context_tags": ["command"],
                        "todo_list": [],
                        "world_state": {},
                    }
                )
                self.assertEqual(world_state["pending_approvals"][0]["id"], approval["id"])

                applied = approve_pending_approval(session_id, approval["id"])
                self.assertEqual(applied["status"], "applied")
                self.assertEqual((root / "out" / "result.txt").read_text(encoding="utf-8"), "hello")

    def test_rejected_file_writeback_does_not_copy(self):
        session_id = "unit-approval-reject"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            session_dir = root / ".data" / "sessions" / session_id
            work_dir = session_dir / "sandbox_work" / "shared"
            work_dir.mkdir(parents=True)
            (work_dir / "result.txt").write_text("hello", encoding="utf-8")

            with patch("app.tools.sandbox.ROOT_DIR", root), patch("app.runtime_paths.SESSIONS_DATA_DIR", root / ".data" / "sessions"):
                approval = create_file_writeback_approval(session_id, "result.txt", "out/result.txt")
                rejected = reject_approval(session_id, approval["id"])

            self.assertEqual(rejected["status"], "rejected")
            self.assertFalse((root / "out" / "result.txt").exists())

    def test_filesystem_access_approval_controls_shared_mount_creation(self):
        session_id = "unit-fs-approval"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shared = root / "shared"
            shared.mkdir()

            with patch("app.runtime_paths.SESSIONS_DATA_DIR", root / ".data" / "sessions"):
                approval = create_filesystem_access_approval(session_id, "docs", str(shared))
                self.assertEqual(approval["type"], "filesystem_access")
                self.assertEqual(list_shared_mounts(session_id), [])

                approved = approve_pending_approval(session_id, approval["id"])
                mounts = list_shared_mounts(session_id)

            self.assertEqual(approved["status"], "approved")
            self.assertEqual(mounts[0]["name"], "docs")
            self.assertEqual(Path(mounts[0]["host_path"]), shared.resolve())

    def test_shared_writeback_requires_authorized_mount(self):
        session_id = "unit-approval-shared"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shared = root / "shared"
            shared.mkdir()
            session_dir = root / ".data" / "sessions" / session_id
            work_dir = session_dir / "sandbox_work" / "shared"
            work_dir.mkdir(parents=True)
            (work_dir / "result.txt").write_text("shared hello", encoding="utf-8")

            with patch("app.tools.sandbox.ROOT_DIR", root), patch("app.runtime_paths.SESSIONS_DATA_DIR", root / ".data" / "sessions"):
                with self.assertRaises(SandboxError):
                    create_file_writeback_approval(session_id, "result.txt", "shared://docs/result.txt")

                add_shared_mount("docs", str(shared), session_id=session_id)
                approval = create_file_writeback_approval(session_id, "result.txt", "shared://docs/result.txt")
                self.assertEqual(approval["target_uri"], "shared://docs/result.txt")
                self.assertFalse((shared / "result.txt").exists())

                applied = approve_pending_approval(session_id, approval["id"])

            self.assertEqual(applied["status"], "applied")
            self.assertEqual((shared / "result.txt").read_text(encoding="utf-8"), "shared hello")


if __name__ == "__main__":
    unittest.main()
