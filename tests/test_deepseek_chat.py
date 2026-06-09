import os
import unittest

os.environ.setdefault("LLM_MODEL_NAME", "gpt-4o-mini")
os.environ.setdefault("LLM_API_KEY", "dummy")
os.environ.setdefault("TAVILY_API_KEY", "dummy")

from langchain_core.messages import AIMessageChunk

from app.config import get_llm_client, normalize_llm_settings
from app.deepseek_chat import ChatDeepSeekReasoning
from app.llm_streaming import extract_thinking_and_content


class DeepSeekReasoningChunkTests(unittest.TestCase):
    def test_deepseek_client_is_used_for_deepseek_provider(self):
        settings = normalize_llm_settings({"provider": "deepseek", "model_name": "deepseek-v4-flash"})
        client = get_llm_client(settings)

        self.assertIsInstance(client, ChatDeepSeekReasoning)

    def test_preserves_reasoning_content_delta_in_chunk_kwargs(self):
        client = ChatDeepSeekReasoning(model="deepseek-v4-flash", api_key="dummy", base_url="https://api.deepseek.com/v1")
        generation_chunk = client._convert_chunk_to_generation_chunk(
            {
                "choices": [
                    {
                        "delta": {
                            "role": "assistant",
                            "reasoning_content": "先分析",
                            "content": "",
                        },
                        "finish_reason": None,
                    }
                ]
            },
            AIMessageChunk,
            {},
        )

        self.assertIsNotNone(generation_chunk)
        thinking, content = extract_thinking_and_content(generation_chunk)
        self.assertEqual(thinking, "先分析")
        self.assertEqual(content, "")

    def test_prefers_reasoning_alias_when_delta_contains_multiple_fields(self):
        client = ChatDeepSeekReasoning(model="deepseek-v4-flash", api_key="dummy", base_url="https://api.deepseek.com/v1")
        generation_chunk = client._convert_chunk_to_generation_chunk(
            {
                "choices": [
                    {
                        "delta": {
                            "reasoning": "当前字段推理",
                            "reasoning_content": "标准字段推理",
                            "content": "",
                        },
                        "finish_reason": None,
                    }
                ]
            },
            AIMessageChunk,
            {},
        )

        thinking, _ = extract_thinking_and_content(generation_chunk)
        self.assertEqual(thinking, "当前字段推理")

    def test_preserves_reasoning_aliases(self):
        client = ChatDeepSeekReasoning(model="deepseek-v4-flash", api_key="dummy", base_url="https://api.deepseek.com/v1")
        generation_chunk = client._convert_chunk_to_generation_chunk(
            {
                "choices": [
                    {
                        "delta": {
                            "reasoning": "别名推理",
                            "content": "",
                        },
                        "finish_reason": None,
                    }
                ]
            },
            AIMessageChunk,
            {},
        )

        thinking, _ = extract_thinking_and_content(generation_chunk)
        self.assertEqual(thinking, "别名推理")


if __name__ == "__main__":
    unittest.main()
