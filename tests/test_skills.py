import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Set up environment variables
os.environ.setdefault("LLM_MODEL_NAME", "gpt-4o-mini")
os.environ.setdefault("LLM_API_KEY", "dummy")
os.environ.setdefault("TAVILY_API_KEY", "dummy")

from langchain_core.runnables import RunnableConfig
from app.memory import store
from app.nodes.common import get_system_prompt
from app.tools.skills import save_skill_sop, list_skills, delete_skill_sop, get_skill_sop


class SkillsMechanismTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.skills_dir = Path(self.tmpdir.name) / "skills"
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        # Patch SKILLS_DIR in store and tools.skills
        self.patch_store = patch("app.memory.store.SKILLS_DIR", self.skills_dir)
        self.patch_tools = patch("app.tools.skills.SKILLS_DIR", self.skills_dir)
        self.patch_store.start()
        self.patch_tools.start()

    def tearDown(self):
        self.patch_tools.stop()
        self.patch_store.stop()
        self.tmpdir.cleanup()

    def test_load_dynamic_skills_filtering(self):
        # Create a matching skill file
        skill_1 = self.skills_dir / "test_python.md"
        skill_1.write_text(
            "---\n"
            "name: test_python\n"
            "description: Python guidelines.\n"
            "tags: [python, tool_error]\n"
            "---\n\n"
            "Python body SOP",
            encoding="utf-8"
        )

        # Create a non-matching skill file
        skill_2 = self.skills_dir / "test_git.md"
        skill_2.write_text(
            "---\n"
            "name: test_git\n"
            "description: Git workflow.\n"
            "tags: [git]\n"
            "---\n\n"
            "Git body SOP",
            encoding="utf-8"
        )

        # Call load_dynamic_skills with "python" tag
        result = store.load_dynamic_skills(["python"])
        self.assertIn("Python body SOP", result)
        self.assertNotIn("Git body SOP", result)
        self.assertIn("test_python", result)
        self.assertIn("python, tool_error", result)

    def test_load_dynamic_skills_handles_malformed_yaml(self):
        # Create a malformed skill file
        skill_malformed = self.skills_dir / "malformed.md"
        skill_malformed.write_text(
            "---\n"
            "name: malformed\n"
            "description: malformed yaml\n"
            "tags: [python\n" # Missing closing bracket
            "---\n\n"
            "Malformed SOP",
            encoding="utf-8"
        )

        # Loader should not crash and just return empty string or other valid skills
        result = store.load_dynamic_skills(["python"])
        self.assertEqual(result, "")

    def test_get_system_prompt_includes_skills(self):
        # Create a matching skill
        skill_1 = self.skills_dir / "test_python.md"
        skill_1.write_text(
            "---\n"
            "name: test_python\n"
            "description: Python guidelines.\n"
            "tags: [python]\n"
            "---\n\n"
            "Python body SOP",
            encoding="utf-8"
        )

        # Prompt should include skills block
        prompt = get_system_prompt("agent_brain", context_tags=["python"])
        self.assertIn("【活跃技能 SOP（根据上下文自动加载）】", prompt)
        self.assertIn("Python body SOP", prompt)

    @patch("app.tools.skills.store_tool_result_for_current_session")
    @patch("app.tools.skills.get_session_id_from_config_or_context")
    async def test_save_skill_sop_tool(self, mock_session, mock_store):
        config = RunnableConfig(configurable={"session_id": "test-session"})

        # Run tool
        result = await save_skill_sop.ainvoke({
            "name": "new_skill",
            "description": "A new skill description",
            "tags": ["docker", "deployment"],
            "instructions": "Docker instructions here"
        }, config=config)

        self.assertIn("成功: 技能 SOP 'new_skill'", result)

        # Verify file is written
        written_file = self.skills_dir / "new_skill.md"
        self.assertTrue(written_file.exists())

        content = written_file.read_text(encoding="utf-8")
        self.assertIn("name: new_skill", content)
        self.assertIn("description: A new skill description", content)
        self.assertIn("tags:", content)
        self.assertIn("docker", content)
        self.assertIn("deployment", content)
        self.assertIn("Docker instructions here", content)

    @patch("app.tools.skills.store_tool_result_for_current_session")
    @patch("app.tools.skills.get_session_id_from_config_or_context")
    async def test_list_skills_tool(self, mock_session, mock_store):
        config = RunnableConfig(configurable={"session_id": "test-session"})

        # Write a dummy skill first
        skill_1 = self.skills_dir / "dummy_skill.md"
        skill_1.write_text(
            "---\n"
            "name: dummy_skill\n"
            "description: Dummy description.\n"
            "tags: [dummy_tag]\n"
            "---\n\n"
            "Dummy body",
            encoding="utf-8"
        )

        # Run tool
        result = await list_skills.ainvoke({}, config=config)

        self.assertIn("可用技能 SOP 列表:", result)
        self.assertIn("dummy_skill", result)
        self.assertIn("Dummy description", result)
        self.assertIn("dummy_tag", result)

    @patch("app.tools.skills.store_tool_result_for_current_session")
    @patch("app.tools.skills.get_session_id_from_config_or_context")
    async def test_delete_skill_sop_tool(self, mock_session, mock_store):
        config = RunnableConfig(configurable={"session_id": "test-session"})

        # Write a dummy skill first
        skill_1 = self.skills_dir / "to_delete.md"
        skill_1.write_text(
            "---\n"
            "name: to_delete\n"
            "description: To delete description.\n"
            "tags: [temp_tag]\n"
            "---\n\n"
            "Temp body",
            encoding="utf-8"
        )
        self.assertTrue(skill_1.exists())

        # Run delete tool
        result = await delete_skill_sop.ainvoke({"name": "to_delete"}, config=config)
        self.assertIn("成功: 技能 SOP 'to_delete' 已删除", result)
        self.assertFalse(skill_1.exists())

    @patch("app.tools.skills.store_tool_result_for_current_session")
    @patch("app.tools.skills.get_session_id_from_config_or_context")
    async def test_get_skill_sop_tool(self, mock_session, mock_store):
        config = RunnableConfig(configurable={"session_id": "test-session"})

        # Write a dummy skill first
        skill_1 = self.skills_dir / "to_view.md"
        skill_1.write_text(
            "---\n"
            "name: to_view\n"
            "description: To view description.\n"
            "tags: [temp_tag]\n"
            "---\n\n"
            "Temp body content",
            encoding="utf-8"
        )
        self.assertTrue(skill_1.exists())

        # Run get tool
        result = await get_skill_sop.ainvoke({"name": "to_view"}, config=config)
        self.assertIn("name: to_view", result)
        self.assertIn("Temp body content", result)

        # Test non-existent skill
        result_err = await get_skill_sop.ainvoke({"name": "non_existent"}, config=config)
        self.assertIn("错误: 技能 SOP 'non_existent' 不存在", result_err)

        # Test invalid name
        result_inv = await get_skill_sop.ainvoke({"name": "../invalid"}, config=config)
        self.assertIn("错误: 技能名称 '../invalid' 不合法", result_inv)


if __name__ == "__main__":
    unittest.main()

