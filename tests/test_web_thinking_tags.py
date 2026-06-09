import asyncio
import os
import unittest

os.environ.setdefault("LLM_MODEL_NAME", "gpt-4o-mini")
os.environ.setdefault("LLM_API_KEY", "dummy")
os.environ.setdefault("TAVILY_API_KEY", "dummy")

from app.web import ConsoleSession, parse_thinking_content


class WebThinkingTagTests(unittest.TestCase):
    def test_parse_thinking_content_handles_multiple_blocks(self):
        thinking, message = parse_thinking_content("前缀<think>先想</think>答案<think>再想</think>结束")

        self.assertEqual(thinking, "先想再想")
        self.assertEqual(message, "前缀答案结束")

    def test_parse_thinking_content_handles_open_streaming_block(self):
        thinking, message = parse_thinking_content("<think>流式推理中")

        self.assertEqual(thinking, "流式推理中")
        self.assertEqual(message, "")

    def test_update_node_llm_run_reparses_server_think_tags_while_streaming(self):
        async def run_case():
            session = ConsoleSession("unit-think-tags")
            await session.start_node_llm_run("agent", ["prompt"])
            for token in ("<think>", "先想", "</think>", "最终回答"):
                await session.update_node_llm_run(token)
            return session.state["events"][-1]["details"]["llm_run"]

        llm_run = asyncio.run(run_case())

        self.assertEqual(llm_run["think"], "先想")
        self.assertEqual(llm_run["message"], "最终回答")
        self.assertEqual(llm_run["content"], "<think>先想</think>最终回答")


if __name__ == "__main__":
    unittest.main()
