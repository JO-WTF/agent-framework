import os
import unittest
from unittest.mock import patch

os.environ.setdefault("LLM_MODEL_NAME", "gpt-4o-mini")
os.environ.setdefault("LLM_API_KEY", "dummy")
os.environ.setdefault("TAVILY_API_KEY", "dummy")

from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage, ToolMessage

from app.cli import route_after_orchestrator
from app.nodes.memory_manager import build_world_state, memory_manager_node, route_after_memory
from app.nodes.common import format_todo_context
from app.nodes.orchestrator import orchestrator_node
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
        self.assertIn("task_ledger", world_state)
        self.assertIn("memory", world_state)
        self.assertEqual(world_state["task_ledger"]["active_agent_role"], "general")
        self.assertEqual(world_state["memory"]["policy"]["hot_path"], "rule_based_no_llm")

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
  "status": "running",
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
        agent_final_reply_state = {
            "messages": [AIMessage(content="任务已完成", id="m1")],
            "last_node": "agent",
        }

        self.assertEqual(route_after_memory(tool_message_state), "agent")
        self.assertEqual(route_after_memory(tool_output_state), "agent")
        self.assertEqual(route_after_memory(agent_tool_call_state), "tools")
        self.assertEqual(route_after_memory(agent_final_reply_state), "orchestrator")

    async def test_orchestrator_fast_path_routes_final_reply_to_evaluator_without_llm(self):
        state = {
            "messages": [AIMessage(content="任务已完成", id="m1")],
            "revision_count": 0,
            "eval_status": "",
            "session_id": "unit-test",
            "task_complexity": "simple",
            "context_tags": ["general"],
            "todo_list": [{"id": "1", "title": "回答用户", "status": "completed", "children": []}],
            "world_state": {},
            "last_node": "agent",
            "orchestrator_next": "agent",
            "agent_role": "general",
        }

        with patch("app.nodes.orchestrator.llm_client.ainvoke") as ainvoke:
            result = await orchestrator_node(state, {})

        ainvoke.assert_not_called()
        self.assertEqual(result["last_node"], "orchestrator")
        self.assertEqual(result["orchestrator_next"], "evaluate")
        self.assertEqual(route_after_orchestrator({**state, **result}), "evaluate")

    async def test_orchestrator_fast_path_preserves_network_agent_role(self):
        state = {
            "messages": [AIMessage(content="网络诊断完成", id="m1")],
            "revision_count": 0,
            "eval_status": "",
            "session_id": "unit-test",
            "task_complexity": "simple",
            "context_tags": ["network"],
            "todo_list": [],
            "world_state": {},
            "last_node": "network_specialist_agent",
            "orchestrator_next": "agent",
            "agent_role": "network",
        }

        with patch("app.nodes.orchestrator.llm_client.ainvoke") as ainvoke:
            result = await orchestrator_node(state, {})

        ainvoke.assert_not_called()
        self.assertEqual(result["agent_role"], "network")
        self.assertEqual(result["orchestrator_next"], "evaluate")

    def test_route_after_orchestrator_sends_non_evaluation_updates_to_memory(self):
        state = {
            "messages": [HumanMessage(content="请继续", id="m1")],
            "orchestrator_next": "agent",
        }

        self.assertEqual(route_after_orchestrator(state), "memory")

    def test_memory_router_never_routes_directly_to_evaluator(self):
        state = {
            "messages": [AIMessage(content="最终答复", id="m1")],
            "last_node": "orchestrator",
            "orchestrator_next": "evaluate",
            "agent_role": "general",
        }

        self.assertEqual(route_after_memory(state), "agent")

    async def test_memory_router_defers_global_and_accepts_session_fast_path(self):
        state = {
            "messages": [HumanMessage(content="记住我偏好中文", id="m1")],
            "revision_count": 0,
            "eval_status": "",
            "session_id": "unit-memory-router",
            "task_complexity": "simple",
            "context_tags": ["memory"],
            "todo_list": [],
            "world_state": {},
            "memory_proposals": [
                {
                    "scope": "global",
                    "kind": "preference",
                    "key": "user.preference.language",
                    "value": "中文",
                    "confidence": 0.9,
                    "source_agent": "agent",
                    "evidence": "用户要求记住语言偏好",
                },
                {
                    "scope": "session",
                    "kind": "decision",
                    "key": "session.response_language",
                    "value": "中文",
                    "confidence": 0.9,
                    "source_agent": "agent",
                    "evidence": "当前会话使用中文",
                },
            ],
        }

        world_state = build_world_state(state)
        routed = world_state["memory"]["routed"]
        statuses = {item["proposal"]["key"]: item["status"] for item in routed}

        self.assertEqual(statuses["user.preference.language"], "deferred")
        self.assertEqual(statuses["session.response_language"], "accepted")
        self.assertIn("session.response_language", world_state["memory"]["view"])

    async def test_memory_router_records_conflict_without_overwrite(self):
        state = {
            "messages": [HumanMessage(content="继续", id="m1")],
            "revision_count": 0,
            "eval_status": "",
            "session_id": "unit-memory-conflict",
            "context_tags": ["memory"],
            "world_state": {
                "memory": {
                    "view": {
                        "project.architecture.memory.write_policy": {
                            "value": "agent_direct_write",
                            "scope": "session",
                            "kind": "decision",
                            "owner": "planner",
                            "tags": ["memory"],
                        }
                    }
                }
            },
            "memory_proposals": [
                {
                    "scope": "session",
                    "kind": "decision",
                    "key": "project.architecture.memory.write_policy",
                    "value": "proposal_only",
                    "confidence": 0.95,
                    "source_agent": "reviewer",
                    "owner": "reviewer",
                    "evidence": "reviewer found overwrite risk",
                }
            ],
        }

        world_state = build_world_state(state)

        self.assertEqual(
            world_state["memory"]["view"]["project.architecture.memory.write_policy"]["value"],
            "agent_direct_write",
        )
        self.assertEqual(world_state["memory"]["conflicts"][0]["status"], "needs_arbitration")

    async def test_memory_router_allows_same_owner_task_updates(self):
        state = {
            "messages": [HumanMessage(content="继续", id="m1")],
            "revision_count": 0,
            "eval_status": "",
            "session_id": "unit-memory-version-update",
            "context_tags": ["memory"],
            "world_state": {
                "memory": {
                    "view": {
                        "task.current.active_agent_role": {
                            "value": "general",
                            "scope": "task",
                            "kind": "delegation",
                            "owner": "orchestrator",
                            "tags": ["memory"],
                        }
                    }
                }
            },
            "memory_proposals": [
                {
                    "scope": "task",
                    "kind": "delegation",
                    "key": "task.current.active_agent_role",
                    "value": "network",
                    "confidence": 1.0,
                    "source_agent": "orchestrator",
                    "owner": "orchestrator",
                    "evidence": "orchestrator changed delegate",
                }
            ],
        }

        world_state = build_world_state(state)

        self.assertEqual(world_state["memory"]["view"]["task.current.active_agent_role"]["value"], "network")
        self.assertFalse(world_state["memory"]["conflicts"])

    async def test_todo_context_uses_compact_memory_budget(self):
        state = {
            "messages": [HumanMessage(content="hello", id="m1")],
            "revision_count": 0,
            "eval_status": "",
            "session_id": "unit-compact-context",
            "task_complexity": "complex",
            "context_tags": ["memory"],
            "todo_list": [{"id": "1", "title": "优化 memory", "status": "in_progress", "note": "", "children": []}],
            "world_state": {
                "runtime_environment": {"write_policy": "write safely", "large": "x" * 5000},
                "tool_results": [{"tool_call_id": "tool-1", "summary": "ok"}],
                "memory": {"view": {}, "policy": {"hot_path": "rule_based_no_llm"}},
            },
        }

        context = format_todo_context(state)

        self.assertIn("Compact Memory Context", context)
        self.assertIn("rule_based_no_llm", context)
        self.assertNotIn("x" * 1000, context)


if __name__ == "__main__":
    unittest.main()
