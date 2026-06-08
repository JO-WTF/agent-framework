import os
import unittest
from unittest.mock import patch

os.environ.setdefault("LLM_MODEL_NAME", "gpt-4o-mini")
os.environ.setdefault("LLM_API_KEY", "dummy")
os.environ.setdefault("TAVILY_API_KEY", "dummy")

from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage, ToolMessage

from app.nodes.memory_manager import build_world_state, memory_manager_node, route_after_memory
from app.runtime_paths import get_session_dir


class MemoryManagerTests(unittest.IsolatedAsyncioTestCase):
    async def test_world_state_captures_todo_and_tool_results(self):
        messages = [
            HumanMessage(content="请执行命令", id="m1"),
            ToolMessage(content="标准输出:\nhello", tool_call_id="tool-1", id="m2"),
        ]
        state = {
            "messages": messages,
            "revision_count": 0,
            "eval_status": "",
            "session_id": "unit-test",
            "task_complexity": "complex",
            "context_tags": ["command"],
            "todo_list": [{"id": "1", "title": "执行命令", "status": "completed", "note": "done", "children": []}],
            "world_state": {},
        }

        world_state = build_world_state(state)

        self.assertEqual(world_state["task_complexity"], "complex")
        self.assertEqual(world_state["context_tags"], ["command"])
        self.assertEqual(world_state["todo_list"][0]["status"], "completed")
        self.assertEqual(world_state["tool_results"][0]["tool_call_id"], "tool-1")
        self.assertIn("hello", world_state["tool_results"][0]["summary"])
        self.assertIn("runtime_environment", world_state)
        self.assertIn("repo://", world_state["runtime_environment"]["path_protocols"])
        self.assertEqual(world_state["runtime_environment"]["sandbox_container_paths"]["work"], "/workspace/work")

    async def test_world_state_captures_not_started_sandbox_when_enabled(self):
        state = {
            "messages": [],
            "revision_count": 0,
            "eval_status": "",
            "session_id": "unit-sandbox-not-started",
            "task_complexity": "simple",
            "context_tags": ["command"],
            "todo_list": [],
            "world_state": {},
        }

        with patch.dict(os.environ, {"AGENT_SANDBOX_MODE": "docker"}, clear=False), patch(
            "app.tools.sandbox.inspect_container_running", return_value=True
        ):
            world_state = build_world_state(state)

        self.assertEqual(world_state["sandbox"]["mode"], "docker")
        self.assertEqual(world_state["sandbox"]["status"], "not_started")

    async def test_world_state_captures_running_sandbox_metadata(self):
        session_id = "unit-sandbox-running"
        session_dir = get_session_dir(session_id)
        sandbox_file = session_dir / "sandbox.json"
        sandbox_file.write_text(
            """
{
  "runtime": "docker",
  "container": "agent-sandbox-test",
  "image": "python:3.12-slim",
  "source_dir": "/repo",
  "work_dir": "/repo/.data/sessions/unit-sandbox-running/sandbox_work/shared"
}
""".strip(),
            encoding="utf-8",
        )
        state = {
            "messages": [],
            "revision_count": 0,
            "eval_status": "",
            "session_id": session_id,
            "task_complexity": "simple",
            "context_tags": ["command"],
            "todo_list": [],
            "world_state": {},
        }

        with patch.dict(os.environ, {"AGENT_SANDBOX_MODE": "docker"}, clear=False), patch(
            "app.tools.sandbox.inspect_container_running", return_value=True
        ):
            world_state = build_world_state(state)

        self.assertEqual(world_state["sandbox"]["status"], "running")
        self.assertEqual(world_state["sandbox"]["container"], "agent-sandbox-test")
        self.assertEqual(world_state["sandbox"]["image"], "python:3.12-slim")

    async def test_memory_manager_archives_redundant_early_messages(self):
        messages = [HumanMessage(content=f"历史 {idx}", id=f"m{idx}") for idx in range(14)]
        state = {
            "messages": messages,
            "revision_count": 0,
            "eval_status": "",
            "session_id": "unit-test",
            "task_complexity": "complex",
            "context_tags": ["general"],
            "todo_list": [{"id": "1", "title": "已确认事实", "status": "completed", "note": "固化", "children": []}],
            "world_state": {},
        }

        with patch("app.nodes.memory_manager.enqueue_archive") as enqueue_archive:
            result = await memory_manager_node(state)

        self.assertIn("world_state", result)
        self.assertIn("messages", result)
        self.assertTrue(all(isinstance(message, RemoveMessage) for message in result["messages"]))
        self.assertGreater(len(result["messages"]), 0)
        enqueue_archive.assert_called_once()

    async def test_memory_manager_skips_cleanup_without_solidified_state(self):
        messages = [HumanMessage(content=f"历史 {idx}", id=f"m{idx}") for idx in range(14)]
        state = {
            "messages": messages,
            "revision_count": 0,
            "eval_status": "",
            "session_id": "unit-test",
            "task_complexity": "unknown",
            "context_tags": ["general"],
            "todo_list": [],
            "world_state": {},
        }

        result = await memory_manager_node(state)

        self.assertIn("world_state", result)
        self.assertNotIn("messages", result)

    def test_route_after_memory_uses_origin_node(self):
        tool_message_state = {
            "messages": [ToolMessage(content="ok", tool_call_id="tool-1", id="m1")],
            "last_node": "orchestrator",
            "orchestrator_next": "agent",
        }
        tool_output_state = {
            "messages": [ToolMessage(content="ok", tool_call_id="tool-1", id="m1")],
            "last_node": "tools",
        }
        agent_tool_call_state = {
            "messages": [AIMessage(content="", tool_calls=[{"id": "call-1", "name": "run_command", "args": {}}], id="m1")],
            "last_node": "agent",
        }

        self.assertEqual(route_after_memory(tool_message_state), "agent")
        self.assertEqual(route_after_memory(tool_output_state), "orchestrator")
        self.assertEqual(route_after_memory(agent_tool_call_state), "tools")


if __name__ == "__main__":
    unittest.main()
