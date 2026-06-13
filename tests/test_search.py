import unittest
from unittest.mock import patch

from app.tools.search import search_web


class SearchToolTests(unittest.IsolatedAsyncioTestCase):
    @patch("app.tools.search.store_tool_result_for_current_session")
    @patch("app.tools.search.get_session_id_from_config_or_context")
    @patch("app.tools.search.search_client")
    async def test_search_web_includes_source_urls(self, search_client, _session_mock, _store_mock):
        search_client.search.return_value = {
            "results": [
                {
                    "title": "Example",
                    "content": "Result summary",
                    "url": "https://example.com/result",
                }
            ]
        }

        result = await search_web.ainvoke({"query": "example"}, config={})

        self.assertIn("Example", result)
        self.assertIn("Result summary", result)
        self.assertIn("来源: https://example.com/result", result)


if __name__ == "__main__":
    unittest.main()
