import os
import unittest
from unittest.mock import patch

os.environ.setdefault("LLM_MODEL_NAME", "gpt-4o-mini")
os.environ.setdefault("LLM_API_KEY", "dummy")
os.environ.setdefault("TAVILY_API_KEY", "dummy")

from langchain_core.messages import AIMessage, HumanMessage

from app.nodes.evaluator import evaluate_response_node


class FakeEvaluatorLLM:
    def __init__(self, response):
        self.response = response
        self.messages = None

    async def ainvoke(self, messages, config):
        self.messages = messages
        return self.response


class EvaluatorThinkingTests(unittest.IsolatedAsyncioTestCase):
    async def test_evaluator_returns_thinking_message_and_prompt(self):
        fake_llm = FakeEvaluatorLLM(AIMessage(content="<think>审查理由</think>PASS"))
        state = {
            "messages": [HumanMessage(content="问题"), AIMessage(content="回答")],
            "revision_count": 0,
            "todo_list": [],
            "task_complexity": "simple",
            "context_tags": ["general"],
            "world_state": {},
        }

        with patch("app.nodes.evaluator.llm_client", fake_llm):
            result = await evaluate_response_node(state, {})

        self.assertEqual(result["eval_status"], "PASS")
        self.assertEqual(result["evaluator_think"], "审查理由")
        self.assertEqual(result["evaluator_message"], "PASS")
        self.assertEqual(result["evaluator_prompt"][0]["role"], "system")
        self.assertEqual(result["evaluator_prompt"][1]["role"], "user")

    async def test_evaluator_reject_uses_message_without_think_tags(self):
        fake_llm = FakeEvaluatorLLM(AIMessage(content="<think>发现缺少信息</think>REJECT: 信息不足"))
        state = {
            "messages": [HumanMessage(content="问题"), AIMessage(content="回答")],
            "revision_count": 0,
            "todo_list": [],
            "task_complexity": "simple",
            "context_tags": ["general"],
            "world_state": {},
        }

        with patch("app.nodes.evaluator.llm_client", fake_llm):
            result = await evaluate_response_node(state, {})

        self.assertEqual(result["eval_status"], "REJECT")
        self.assertEqual(result["evaluator_think"], "发现缺少信息")
        self.assertEqual(result["evaluator_message"], "REJECT: 信息不足")
        self.assertIn("信息不足", result["messages"][0].content)


if __name__ == "__main__":
    unittest.main()
