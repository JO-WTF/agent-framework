import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.tools.context import set_session_id
from app.tools.storage import (
    list_tool_results_for_current_session,
    read_tool_result_for_current_session,
    store_tool_result_for_current_session,
)


class ToolResultStorageTests(unittest.TestCase):
    def test_reads_archived_tool_result_by_ref_id_with_pagination(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("app.runtime_paths.SESSIONS_DATA_DIR", root / ".data" / "sessions"):
                set_session_id("unit-tool-result")
                ref_id = store_tool_result_for_current_session("run_command", "0123456789", {"command": "printf"})

                listed = list_tool_results_for_current_session(limit=5)
                self.assertEqual(listed[0]["id"], ref_id)
                self.assertEqual(listed[0]["content_length"], 10)

                first = read_tool_result_for_current_session(ref_id, offset=0, limit=4)
                self.assertEqual(first["content"], "0123")
                self.assertTrue(first["has_more"])
                self.assertEqual(first["next_offset"], 4)

                second = read_tool_result_for_current_session(ref_id, offset=4, limit=10)
                self.assertEqual(second["content"], "456789")
                self.assertFalse(second["has_more"])


if __name__ == "__main__":
    unittest.main()
