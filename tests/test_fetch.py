import json
import unittest
from unittest.mock import patch

from langchain_core.runnables import RunnableConfig

from app.tools.fetch import fetch_url
from app.tools.sandbox import SandboxResult


class FetchUrlToolTests(unittest.IsolatedAsyncioTestCase):
    @patch("app.tools.fetch.store_tool_result_for_current_session", return_value="tool-0001")
    @patch("app.tools.fetch.get_session_id_from_config_or_context")
    @patch("app.tools.fetch.run_sandboxed_python")
    async def test_fetch_url_returns_page_text_and_metadata(self, run_python, _session_mock, _store_mock):
        run_python.return_value = SandboxResult(
            stdout=json.dumps(
                {
                    "success": True,
                    "url": "https://example.com/page",
                    "status_code": 200,
                    "content_type": "text/html",
                    "title": "Example Page",
                    "text": "Readable body",
                    "content_length": 13,
                    "truncated": False,
                }
            ),
            stderr="",
            returncode=0,
        )

        result = await fetch_url.ainvoke({"url": "https://example.com/page"}, config=RunnableConfig(configurable={"session_id": "s"}))

        self.assertIn("状态码: 200", result)
        self.assertIn("标题: Example Page", result)
        self.assertIn("Readable body", result)


if __name__ == "__main__":
    unittest.main()
