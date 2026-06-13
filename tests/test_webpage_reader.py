import os
import unittest
from unittest.mock import patch

os.environ.setdefault("LLM_MODEL_NAME", "gpt-4o-mini")
os.environ.setdefault("LLM_API_KEY", "dummy")
os.environ.setdefault("TAVILY_API_KEY", "dummy")

from langchain_core.runnables import RunnableConfig

from app.tools.webpage_reader import extract_readable_webpage, read_webpage


class WebpageReaderTests(unittest.IsolatedAsyncioTestCase):
    def test_fallback_extractor_removes_code_and_noise(self):
        html = """
        <html>
          <head><title>Example Article</title><meta name="description" content="Short desc"></head>
          <body>
            <nav>Home Pricing Login</nav>
            <article>
              <h1>Main Heading</h1>
              <p>This is the useful article body.</p>
              <pre>print("do not include")</pre>
              <code>const hidden = true</code>
              <p>Second paragraph with details.</p>
            </article>
            <footer>Copyright footer</footer>
          </body>
        </html>
        """

        extracted = extract_readable_webpage(html, url="https://example.com/article")

        self.assertEqual(extracted["title"], "Example Article")
        self.assertEqual(extracted["description"], "Short desc")
        self.assertIn("Main Heading", extracted["text"])
        self.assertIn("useful article body", extracted["text"])
        self.assertNotIn("do not include", extracted["text"])
        self.assertNotIn("hidden", extracted["text"])
        self.assertNotIn("Home Pricing Login", extracted["text"])
        self.assertNotIn("Copyright footer", extracted["text"])

    @patch("app.tools.webpage_reader.store_tool_result_for_current_session", return_value="tool-1234")
    @patch("app.tools.webpage_reader.get_session_id_from_config_or_context")
    @patch("app.tools.webpage_reader._fetch_html")
    async def test_read_webpage_stores_full_result_and_returns_preview(self, mock_fetch, mock_session, mock_store):
        body = " ".join(["正文内容"] * 500)
        html = f"""
        <html>
          <head><title>Long Page</title></head>
          <body><main><h1>Readable</h1><p>{body}</p><script>alert(1)</script></main></body>
        </html>
        """
        mock_fetch.return_value = (200, {"content-type": "text/html"}, html)

        result = await read_webpage.ainvoke(
            {"url": "https://example.com/long", "max_chars": 800},
            config=RunnableConfig(configurable={"session_id": "test-session"}),
        )

        self.assertIn("状态码: 200", result)
        self.assertIn("标题: Long Page", result)
        self.assertIn("完整提取结果已保存为引用 tool-1234", result)
        self.assertIn("read_tool_result(ref_id=\"tool-1234\")", result)
        self.assertNotIn("<script>", result)
        mock_store.assert_called_once()
        stored_content = mock_store.call_args[0][1]
        self.assertIn("正文内容", stored_content)
        self.assertNotIn("alert(1)", stored_content)


if __name__ == "__main__":
    unittest.main()
