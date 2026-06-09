import unittest
from types import SimpleNamespace
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.llm_logging import log_llm_request, log_llm_response, log_user_question


class LLMLoggingTests(unittest.TestCase):
    def test_logs_user_prompt_messages(self):
        messages = [SystemMessage(content="sys"), HumanMessage(content="用户问题")]

        with patch("app.llm_logging.logger") as logger:
            log_llm_request("unit", messages)

        logged = logger.info.call_args.args
        self.assertIn("unit", logged)
        self.assertIn("用户问题", logged)

    def test_logs_thinking_and_response_without_think_tags(self):
        response = AIMessage(content="<think>先想</think>最终回答")

        with patch("app.llm_logging.logger") as logger:
            log_llm_response("unit", response)

        logged = logger.info.call_args.args
        self.assertIn("先想", logged)
        self.assertIn("最终回答", logged)
        self.assertNotIn("<think>", logged)

    def test_logs_additional_reasoning_content(self):
        response = SimpleNamespace(content="最终回答", additional_kwargs={"reasoning_content": "推理"})

        with patch("app.llm_logging.logger") as logger:
            log_llm_response("unit", response)

        logged = logger.info.call_args.args
        self.assertIn("推理", logged)
        self.assertIn("最终回答", logged)

    def test_logs_user_question(self):
        with patch("app.llm_logging.logger") as logger:
            log_user_question("web", "用户提问")

        logged = logger.info.call_args.args
        self.assertIn("web", logged)
        self.assertIn("用户提问", logged)


if __name__ == "__main__":
    unittest.main()
