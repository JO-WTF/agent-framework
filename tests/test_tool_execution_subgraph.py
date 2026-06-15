import os
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("LLM_MODEL_NAME", "gpt-4o-mini")
os.environ.setdefault("LLM_API_KEY", "dummy")
os.environ.setdefault("TAVILY_API_KEY", "dummy")

from langchain_core.messages import AIMessage, ToolMessage

from app.nodes.tool_execution_subgraph import classify_tool_result, tool_execution_subgraph, validate_fixed_args
from app.nodes.tools_node import tools_execution_node
from app.tools.command_runner import run_command
from app.tools.context import get_session_id
from app.tools.sandbox import SandboxResult


class ToolExecutionSubgraphTests(unittest.IsolatedAsyncioTestCase):
    async def test_subgraph_executes_tool_and_keeps_internal_messages_private(self):
        with patch(
            "app.tools.command_runner.run_sandboxed_command",
            return_value=SandboxResult(stdout="hello", stderr="", returncode=0, metadata={"runtime": "docker"}),
        ):
            result = await tool_execution_subgraph.ainvoke(
                {
                    "original_request": {
                        "id": "call-1",
                        "name": "run_command",
                        "args": {"command": "printf hello"},
                    },
                    "tool_call_id": "call-1",
                    "tool_name": "run_command",
                    "args": {"command": "printf hello"},
                    "session_id": "unit-test",
                    "retry_count": 0,
                    "max_retries": 0,
                    "internal_messages": [],
                    "status": "pending",
                    "final_result": "",
                }
            )

        self.assertEqual(result["status"], "success")
        self.assertIn("hello", result["final_result"])
        self.assertIn("internal_messages", result)

    @patch("app.tools.command_runner.store_tool_result_for_current_session", return_value="tool-0001")
    @patch("app.tools.command_runner.get_session_id_from_config_or_context")
    @patch(
        "app.tools.command_runner.run_sandboxed_command",
        return_value=SandboxResult(stdout="", stderr="cat: missing: No such file", returncode=1, metadata={"runtime": "docker"}),
    )
    async def test_run_command_marks_nonzero_exit_as_failure(self, _run_mock, _session_mock, _store_mock):
        result = await run_command.ainvoke({"command": "cat missing"}, config={})

        self.assertIn("执行失败: 命令退出码 1", result)
        self.assertIn("标准错误:", result)

    async def test_tools_node_returns_only_tool_messages_for_parent_graph(self):
        message = AIMessage(
            content="",
            tool_calls=[
                {
                    "id": "call-1",
                    "name": "run_command",
                    "args": {"command": "printf one"},
                },
                {
                    "id": "call-2",
                    "name": "run_command",
                    "args": {"command": "printf two"},
                },
            ],
        )

        side_effects = [
            SandboxResult(stdout="one", stderr="", returncode=0, metadata={"runtime": "docker"}),
            SandboxResult(stdout="two", stderr="", returncode=0, metadata={"runtime": "docker"}),
        ]
        with patch("app.tools.command_runner.run_sandboxed_command", side_effect=side_effects):
            result = await tools_execution_node(
                {
                    "messages": [message],
                    "revision_count": 0,
                    "eval_status": "",
                    "session_id": "unit-test",
                },
                {},
            )

        self.assertEqual(len(result["messages"]), 2)
        self.assertTrue(all(isinstance(item, ToolMessage) for item in result["messages"]))
        self.assertEqual([item.tool_call_id for item in result["messages"]], ["call-1", "call-2"])
        self.assertNotIn("internal_messages", result)
        self.assertIn("one", result["messages"][0].content)
        self.assertIn("two", result["messages"][1].content)

    async def test_tools_node_runs_safe_readonly_tools_concurrently_preserving_order(self):
        message = AIMessage(
            content="",
            tool_calls=[
                {"id": "call-1", "name": "search_web", "args": {"query": "one"}},
                {"id": "call-2", "name": "read_tool_result", "args": {"ref_id": "tool-0001"}},
            ],
        )

        async def fake_ainvoke(payload, config=None):
            await __import__("asyncio").sleep(0.05)
            return {"final_result": f"result {payload['tool_call_id']}"}

        started = time.perf_counter()
        with patch("app.nodes.tools_node.tool_execution_subgraph.ainvoke", side_effect=fake_ainvoke):
            result = await tools_execution_node(
                {
                    "messages": [message],
                    "revision_count": 0,
                    "eval_status": "",
                    "session_id": "unit-test",
                },
                {},
            )
        elapsed = time.perf_counter() - started

        self.assertLess(elapsed, 0.09)
        self.assertEqual([item.tool_call_id for item in result["messages"]], ["call-1", "call-2"])
        self.assertEqual([item.content for item in result["messages"]], ["result call-1", "result call-2"])

    async def test_unknown_tool_returns_failure_tool_message(self):
        message = AIMessage(
            content="",
            tool_calls=[
                {
                    "id": "missing-call",
                    "name": "missing_tool",
                    "args": {},
                }
            ],
        )

        result = await tools_execution_node(
            {
                "messages": [message],
                "revision_count": 0,
                "eval_status": "",
                "session_id": "unit-test",
            },
            {},
        )

        self.assertEqual(len(result["messages"]), 1)
        self.assertEqual(result["messages"][0].tool_call_id, "missing-call")
        self.assertIn("未找到工具 missing_tool", result["messages"][0].content)

    async def test_tool_execution_node_sets_session_id(self):
        message = AIMessage(
            content="",
            tool_calls=[
                {
                    "id": "call-1",
                    "name": "run_command",
                    "args": {"command": "printf session"},
                }
            ],
        )

        await tools_execution_node(
            {
                "messages": [message],
                "revision_count": 0,
                "eval_status": "",
                "session_id": "custom-session",
            },
            {},
        )

        self.assertEqual(get_session_id(), "custom-session")

    async def test_subgraph_catches_tool_exceptions(self):
        class ExplodingTool:
            name = "explode"

            async def ainvoke(self, args, config=None):
                raise RuntimeError("boom")

        with patch("app.nodes.tool_execution_subgraph.TOOLS_BY_NAME", {"explode": ExplodingTool()}):
            result = await tool_execution_subgraph.ainvoke(
                {
                    "original_request": {
                        "id": "call-1",
                        "name": "explode",
                        "args": {},
                    },
                    "tool_call_id": "call-1",
                    "tool_name": "explode",
                    "args": {},
                    "session_id": "unit-test",
                    "retry_count": 0,
                    "max_retries": 0,
                    "internal_messages": [],
                    "status": "pending",
                    "final_result": "",
                }
            )

        self.assertEqual(result["status"], "retryable_failure")
        self.assertIn("boom", result["final_result"])

    def test_classifies_string_failures_from_existing_tools(self):
        self.assertEqual(classify_tool_result("run_python", "代码报错:\nTraceback\nNameError: x"), ("retryable_failure", "Python 代码错误，可尝试修复代码参数。"))
        status, reason = classify_tool_result("run_python", "代码报错:\nTraceback\nModuleNotFoundError: No module named 'pandas'")
        self.assertEqual(status, "needs_external_action")
        self.assertIn("pandas", reason)
        self.assertEqual(classify_tool_result("search_web", "未找到相关结果。"), ("retryable_failure", "搜索无结果，可尝试改写查询。"))
        self.assertEqual(classify_tool_result("run_command", "执行失败: 命令退出码 2。"), ("retryable_failure", "命令执行失败，可尝试一次安全参数修复。"))
        self.assertEqual(classify_tool_result("run_command", "命令执行成功 (无输出)。"), ("success", ""))

    def test_rejects_dangerous_command_repairs(self):
        ok, reason = validate_fixed_args(
            "run_command",
            {"command": "cat missing-file"},
            {"command": "rm -rf /tmp/missing-file"},
        )

        self.assertFalse(ok)
        self.assertIn("危险操作", reason)

    async def test_retryable_failure_uses_fix_node_and_retries_with_private_history(self):
        class RepairablePythonTool:
            name = "run_python"

            def __init__(self):
                self.calls = []

            async def ainvoke(self, args, config=None):
                self.calls.append(args)
                if len(self.calls) == 1:
                    return "代码报错:\nTraceback\nNameError: name 'x' is not defined"
                return "修复成功"

        class FakeLLM:
            async def ainvoke(self, messages, config=None):
                return AIMessage(
                    content='{"can_retry": true, "args": {"code": "print(1)"}, "reason": "补充可执行代码"}'
                )

        tool = RepairablePythonTool()
        with patch("app.nodes.tool_execution_subgraph.TOOLS_BY_NAME", {"run_python": tool}), patch(
            "app.nodes.tool_execution_subgraph.llm_client", FakeLLM()
        ):
            result = await tool_execution_subgraph.ainvoke(
                {
                    "original_request": {
                        "id": "call-1",
                        "name": "run_python",
                        "args": {"code": "print(x)"},
                    },
                    "tool_call_id": "call-1",
                    "tool_name": "run_python",
                    "args": {"code": "print(x)"},
                    "session_id": "unit-test",
                    "retry_count": 0,
                    "max_retries": 3,
                    "internal_messages": [],
                    "status": "pending",
                    "final_result": "",
                }
            )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["retry_count"], 1)
        self.assertEqual(tool.calls, [{"code": "print(x)"}, {"code": "print(1)"}])
        self.assertEqual(result["final_result"], "修复成功")
        self.assertIn("internal_messages", result)

    async def test_missing_python_dependency_exits_to_parent_without_fixing(self):
        class MissingDependencyPythonTool:
            name = "run_python"

            def __init__(self):
                self.calls = []

            async def ainvoke(self, args, config=None):
                self.calls.append(args)
                return "代码报错:\nTraceback\nModuleNotFoundError: No module named 'pandas'"

        class FailingLLM:
            async def ainvoke(self, messages, config=None):
                raise AssertionError("fix_node should not run for missing dependencies")

        tool = MissingDependencyPythonTool()
        with patch("app.nodes.tool_execution_subgraph.TOOLS_BY_NAME", {"run_python": tool}), patch(
            "app.nodes.tool_execution_subgraph.llm_client", FailingLLM()
        ):
            result = await tool_execution_subgraph.ainvoke(
                {
                    "original_request": {
                        "id": "call-1",
                        "name": "run_python",
                        "args": {"code": "import pandas as pd\nprint(pd.__version__)"},
                    },
                    "tool_call_id": "call-1",
                    "tool_name": "run_python",
                    "args": {"code": "import pandas as pd\nprint(pd.__version__)"},
                    "session_id": "unit-test",
                    "retry_count": 0,
                    "max_retries": 3,
                    "internal_messages": [],
                    "status": "pending",
                    "final_result": "",
                }
            )

        self.assertEqual(len(tool.calls), 1)
        self.assertEqual(result["status"], "needs_external_action")
        self.assertEqual(result["retry_count"], 0)
        self.assertEqual(result["required_action"]["suggested_tool"], "run_command")
        self.assertIn("pip install pandas", result["required_action"]["command"])
        self.assertIn("不会自动调用 run_command", result["final_result"])


    async def test_dangerous_command_fix_is_not_retried(self):
        class FailingCommandTool:
            name = "run_command"

            def __init__(self):
                self.calls = []

            async def ainvoke(self, args, config=None):
                self.calls.append(args)
                return "执行失败: command not found"

        class FakeLLM:
            async def ainvoke(self, messages, config=None):
                return AIMessage(
                    content='{"can_retry": true, "args": {"command": "rm -rf /tmp/demo"}, "reason": "尝试清理后重试"}'
                )

        tool = FailingCommandTool()
        with patch("app.nodes.tool_execution_subgraph.TOOLS_BY_NAME", {"run_command": tool}), patch(
            "app.nodes.tool_execution_subgraph.llm_client", FakeLLM()
        ):
            result = await tool_execution_subgraph.ainvoke(
                {
                    "original_request": {
                        "id": "call-1",
                        "name": "run_command",
                        "args": {"command": "cat missing-file"},
                    },
                    "tool_call_id": "call-1",
                    "tool_name": "run_command",
                    "args": {"command": "cat missing-file"},
                    "session_id": "unit-test",
                    "retry_count": 0,
                    "max_retries": 1,
                    "internal_messages": [],
                    "status": "pending",
                    "final_result": "",
                }
            )

        self.assertEqual(len(tool.calls), 1)
        self.assertEqual(result["status"], "terminal_failure")
        self.assertIn("危险操作", result["final_result"])


if __name__ == "__main__":
    unittest.main()
