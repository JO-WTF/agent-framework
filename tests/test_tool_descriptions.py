import unittest

from app.config import PROMPTS
from app.tools.registry import AGENT_TOOLS, get_agent_tools


class ToolDescriptionTests(unittest.TestCase):
    def test_registered_tools_have_prompt_descriptions(self):
        prompt_descriptions = PROMPTS.get("tools", {})
        tool_names = {tool.name for tool in AGENT_TOOLS}

        self.assertTrue(tool_names.issubset(set(prompt_descriptions)))
        for name in sorted(tool_names):
            self.assertTrue(prompt_descriptions[name].strip(), name)
            tool = next(tool for tool in AGENT_TOOLS if tool.name == name)
            self.assertEqual(tool.description.strip(), prompt_descriptions[name].strip())

    def test_agent_tool_selection_keeps_general_context_small(self):
        tool_names = {tool.name for tool in get_agent_tools(["general"], recent_text="普通问题")}

        self.assertEqual(
            tool_names,
            {"search_web", "fetch_url", "list_tool_results", "read_tool_result", "run_python", "run_command"},
        )

    def test_agent_tool_selection_adds_sandbox_tools_for_file_work(self):
        tool_names = {tool.name for tool in get_agent_tools(["file_system"], recent_text="需要写回 repo://demo.txt")}

        self.assertIn("add_shared_mount", tool_names)
        self.assertIn("apply_sandbox_file", tool_names)
        self.assertIn("sandbox_status", tool_names)

    def test_agent_tool_selection_adds_skill_tools_by_keyword(self):
        tool_names = {tool.name for tool in get_agent_tools(["general"], recent_text="请把这个流程保存成技能 SOP")}

        self.assertIn("save_skill_sop", tool_names)
        self.assertIn("list_skills", tool_names)


if __name__ == "__main__":
    unittest.main()
