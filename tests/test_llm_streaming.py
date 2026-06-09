import unittest
from types import SimpleNamespace

from app.llm_streaming import extract_thinking_and_content


class LLMStreamingExtractionTests(unittest.TestCase):
    def test_extracts_reasoning_from_direct_message_chunk_attribute(self):
        chunk = SimpleNamespace(reasoning_content="先计算", content="答案是2")

        thinking, content = extract_thinking_and_content(chunk)

        self.assertEqual(thinking, "先计算")
        self.assertEqual(content, "答案是2")

    def test_extracts_thinking_from_chat_generation_chunk_message_kwargs(self):
        message = SimpleNamespace(content="", additional_kwargs={"thinking": "分析中"})
        chunk = SimpleNamespace(message=message, text="")

        thinking, content = extract_thinking_and_content(chunk)

        self.assertEqual(thinking, "分析中")
        self.assertEqual(content, "")

    def test_extracts_reasoning_and_content_from_content_blocks(self):
        chunk = SimpleNamespace(
            content=[
                {"type": "reasoning_content", "text": "推理"},
                {"type": "text", "text": "结果"},
            ],
            additional_kwargs={},
        )

        thinking, content = extract_thinking_and_content(chunk)

        self.assertEqual(thinking, "推理")
        self.assertEqual(content, "结果")

    def test_falls_back_to_generation_chunk_text(self):
        chunk = SimpleNamespace(message=SimpleNamespace(content=""), text="普通token")

        thinking, content = extract_thinking_and_content(chunk)

        self.assertEqual(thinking, "")
        self.assertEqual(content, "普通token")


if __name__ == "__main__":
    unittest.main()
