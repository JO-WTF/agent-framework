import os
import json
import unittest
from unittest.mock import patch

# Set up environment variables
os.environ.setdefault("LLM_MODEL_NAME", "gpt-4o-mini")
os.environ.setdefault("LLM_API_KEY", "dummy")
os.environ.setdefault("TAVILY_API_KEY", "dummy")

from langchain_core.runnables import RunnableConfig
from app.tools.api_request import api_request
from app.tools.sandbox import SandboxResult


class ApiRequestToolTests(unittest.IsolatedAsyncioTestCase):
    @patch("app.tools.api_request.store_tool_result_for_current_session")
    @patch("app.tools.api_request.get_session_id_from_config_or_context")
    @patch("app.tools.api_request.run_sandboxed_python")
    async def test_api_request_tool_sandboxed_success_get(self, mock_run_python, mock_session, mock_store):
        config = RunnableConfig(configurable={"session_id": "test-session"})

        # Mock SandboxResult
        stdout_json = json.dumps({
            "success": True,
            "status_code": 200,
            "text": "Hello World Response",
            "headers": {"Content-Type": "text/plain"}
        })
        mock_run_python.return_value = SandboxResult(
            stdout=stdout_json,
            stderr="",
            returncode=0,
            metadata={"container": "test-container"}
        )

        # Execute api_request tool
        result = await api_request.ainvoke({
            "url": "https://api.example.com/data",
            "method": "GET",
        }, config=config)

        # Assertions
        mock_run_python.assert_called_once()
        # Verify the generated code contains requests and target URL
        called_code = mock_run_python.call_args[0][0]
        self.assertIn("import requests", called_code)
        self.assertIn("https://api.example.com/data", called_code)
        
        self.assertIn("状态码: 200", result)
        self.assertIn("响应内容:", result)
        self.assertIn("Hello World Response", result)

    @patch("app.tools.api_request.store_tool_result_for_current_session")
    @patch("app.tools.api_request.get_session_id_from_config_or_context")
    @patch("app.tools.api_request.run_sandboxed_python")
    async def test_api_request_tool_sandboxed_invalid_method(self, mock_run_python, mock_session, mock_store):
        config = RunnableConfig(configurable={"session_id": "test-session"})

        # Execute with invalid method
        result = await api_request.ainvoke({
            "url": "https://api.example.com/data",
            "method": "INVALID",
        }, config=config)

        self.assertIn("错误: 不支持的 HTTP 方法 'INVALID'", result)
        mock_run_python.assert_not_called()

    @patch("app.tools.api_request.save_agent_note")
    @patch("app.tools.api_request.store_tool_result_for_current_session")
    @patch("app.tools.api_request.get_session_id_from_config_or_context")
    @patch("app.tools.api_request.run_sandboxed_python")
    async def test_api_request_tool_sandboxed_request_error(self, mock_run_python, mock_session, mock_store, mock_note):
        config = RunnableConfig(configurable={"session_id": "test-session"})

        # Mock failed requests in sandbox
        stdout_json = json.dumps({
            "success": False,
            "error": "Connection refused"
        })
        mock_run_python.return_value = SandboxResult(
            stdout=stdout_json,
            stderr="",
            returncode=0
        )
        mock_note.return_value = "note-123"

        # Execute
        result = await api_request.ainvoke({
            "url": "https://api.example.com/data",
            "method": "GET",
        }, config=config)

        self.assertIn("请求失败: Connection refused", result)
        self.assertIn("已记录笔记 note-123", result)

    @patch("app.tools.api_request.store_tool_result_for_current_session")
    @patch("app.tools.api_request.get_session_id_from_config_or_context")
    @patch("app.tools.api_request.run_sandboxed_python")
    async def test_api_request_blocks_html_body_and_points_to_read_webpage(self, mock_run_python, mock_session, mock_store):
        config = RunnableConfig(configurable={"session_id": "test-session"})
        stdout_json = json.dumps({
            "success": True,
            "status_code": 200,
            "text": "<!doctype html><html><body><article>Secret page body</article></body></html>",
            "headers": {"Content-Type": "text/html; charset=utf-8"}
        })
        mock_run_python.return_value = SandboxResult(
            stdout=stdout_json,
            stderr="",
            returncode=0,
            metadata={"container": "test-container"}
        )

        result = await api_request.ainvoke({
            "url": "https://example.com/article",
            "method": "GET",
        }, config=config)

        self.assertIn("api_request 禁止用于获取网页 HTML 主体内容", result)
        self.assertIn("read_webpage", result)
        self.assertNotIn("Secret page body", result)
        mock_store.assert_called_once()
        self.assertEqual(mock_store.call_args[0][2]["status"], "html_blocked_use_read_webpage")
        self.assertNotIn("Secret page body", mock_store.call_args[0][1])


if __name__ == "__main__":
    unittest.main()
