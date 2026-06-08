import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("LLM_MODEL_NAME", "gpt-4o-mini")
os.environ.setdefault("LLM_API_KEY", "dummy")
os.environ.setdefault("TAVILY_API_KEY", "dummy")

from langchain_core.messages import HumanMessage

from app.memory import store
from app.nodes.common import get_system_prompt, infer_context_tags_from_state


class DynamicContextTests(unittest.TestCase):
    def test_static_guidelines_are_selected_by_context_tags(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            guidelines = Path(tmpdir) / "CLAUDE.md"
            guidelines.write_text(
                "# General [general]\n通用规则\n\n"
                "# File Rules [file_system]\n文件系统规则\n\n"
                "# API Rules [api_call]\n接口规则\n",
                encoding="utf-8",
            )

            with patch("app.memory.store.STATIC_GUIDELINES_FILE", guidelines):
                selected = store.load_static_guidelines(["file_system"])

        self.assertIn("文件系统规则", selected)
        self.assertNotIn("接口规则", selected)
        self.assertNotIn("通用规则", selected)

    def test_agent_notes_are_filtered_by_context_tags(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            memory_file = Path(tmpdir) / "agent_memory.json"
            with patch("app.memory.store.GLOBAL_AGENT_MEMORY_FILE", memory_file):
                store.save_agent_note("Python traceback 修复经验", source="run_python", tags=["python", "tool_error"])
                store.save_agent_note("Shell 命令修复经验", source="run_command", tags=["command", "tool_error"])
                selected = store.load_agent_notes(["python"], limit=5)

        self.assertIn("Python traceback 修复经验", selected)
        self.assertNotIn("Shell 命令修复经验", selected)

    def test_system_prompt_uses_lazy_loaded_context_sections(self):
        with patch("app.nodes.common.load_static_guidelines", return_value="文件系统规则"), patch(
            "app.nodes.common.load_agent_notes", return_value="文件系统笔记"
        ):
            prompt = get_system_prompt("agent_brain", context_tags=["file_system"])

        self.assertIn("【动态上下文标签】file_system", prompt)
        self.assertIn("文件系统规则", prompt)
        self.assertIn("文件系统笔记", prompt)

    def test_orchestrator_initial_tags_are_inferred_from_messages(self):
        tags = infer_context_tags_from_state({"messages": [HumanMessage(content="请读取这个文件路径并检查报错")], "todo_list": []})

        self.assertIn("file_system", tags)
        self.assertIn("tool_error", tags)


if __name__ == "__main__":
    unittest.main()
