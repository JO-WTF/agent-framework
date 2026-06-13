import os
import json
import unittest
from unittest.mock import patch, MagicMock

# Set up environment variables
os.environ.setdefault("LLM_MODEL_NAME", "gpt-4o-mini")
os.environ.setdefault("LLM_API_KEY", "dummy")
os.environ.setdefault("TAVILY_API_KEY", "dummy")

from langchain_core.runnables import RunnableConfig
from app.tools.curl import curl
from app.tools.sandbox import SandboxResult


class CurlToolTests(unittest.IsolatedAsyncioTestCase):
    @patch("app.tools.curl.store_tool_result_for_current_session")
    @patch("app.tools.curl.get_session_id_from_config_or_context")
    @patch("app.tools.curl.run_sandboxed_python")
    async def test_curl_tool_sandboxed_success_get(self, mock_run_python, mock_session, mock_store):
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

        # Execute curl tool
        result = await curl.ainvoke({
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

    @patch("app.tools.curl.store_tool_result_for_current_session")
    @patch("app.tools.curl.get_session_id_from_config_or_context")
    @patch("app.tools.curl.run_sandboxed_python")
    async def test_curl_tool_sandboxed_invalid_method(self, mock_run_python, mock_session, mock_store):
        config = RunnableConfig(configurable={"session_id": "test-session"})

        # Execute with invalid method
        result = await curl.ainvoke({
            "url": "https://api.example.com/data",
            "method": "INVALID",
        }, config=config)

        self.assertIn("错误: 不支持的 HTTP 方法 'INVALID'", result)
        mock_run_python.assert_not_called()

    @patch("app.tools.curl.save_agent_note")
    @patch("app.tools.curl.store_tool_result_for_current_session")
    @patch("app.tools.curl.get_session_id_from_config_or_context")
    @patch("app.tools.curl.run_sandboxed_python")
    async def test_curl_tool_sandboxed_request_error(self, mock_run_python, mock_session, mock_store, mock_note):
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
        result = await curl.ainvoke({
            "url": "https://api.example.com/data",
            "method": "GET",
        }, config=config)

        self.assertIn("请求失败: Connection refused", result)
        self.assertIn("已记录笔记 note-123", result)

    @patch("app.tools.curl.save_agent_note")
    @patch("app.tools.curl.store_tool_result_for_current_session")
    @patch("app.tools.curl.get_session_id_from_config_or_context")
    @patch("app.tools.curl.run_sandboxed_python")
    async def test_curl_tool_reports_empty_sandbox_output(self, mock_run_python, mock_session, mock_store, mock_note):
        config = RunnableConfig(configurable={"session_id": "test-session"})
        mock_run_python.return_value = SandboxResult(stdout="", stderr="", returncode=0)
        mock_note.return_value = "note-124"

        result = await curl.ainvoke({
            "url": "https://api.example.com/data",
            "method": "GET",
        }, config=config)

        self.assertIn("请求失败: 沙箱 HTTP 请求未返回结果", result)
        self.assertIn("已记录笔记 note-124", result)


if __name__ == "__main__":
    unittest.main()
