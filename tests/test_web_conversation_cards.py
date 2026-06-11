import os
import unittest

os.environ.setdefault("LLM_MODEL_NAME", "gpt-4o-mini")
os.environ.setdefault("LLM_API_KEY", "dummy")
os.environ.setdefault("TAVILY_API_KEY", "dummy")

from app.web import ConsoleSession


class ConversationCardTests(unittest.IsolatedAsyncioTestCase):
    def test_cards_attach_to_active_conversation_turn(self):
        session = ConsoleSession("conversation-test")
        turn_id = session.start_conversation_turn({"role": "user", "content": "展示仓库地图", "tool_calls": []})

        card = session.add_card_to_active_turn(
            "map",
            {
                "id": "map-001",
                "title": "仓库地图",
                "points": [{"latitude": 31.2304, "longitude": 121.4737, "label": "上海仓"}],
                "lines": [],
            },
        )
        session.complete_conversation_turn({"role": "assistant", "content": "已生成地图。", "tool_calls": []})

        self.assertEqual(card["type"], "map")
        self.assertEqual(session.state["active_turn_id"], turn_id)
        self.assertEqual(len(session.state["conversation_turns"]), 1)
        turn = session.state["conversation_turns"][0]
        self.assertEqual(turn["id"], turn_id)
        self.assertEqual(turn["assistant"]["content"], "已生成地图。")
        self.assertEqual(turn["cards"][0]["type"], "map")
        self.assertEqual(turn["cards"][0]["payload"]["title"], "仓库地图")

    async def test_add_map_card_preserves_flat_list_and_turn_card(self):
        session = ConsoleSession("conversation-test")
        session.start_conversation_turn({"role": "user", "content": "站点地图", "tool_calls": []})

        await session.add_map_card(
            {
                "id": "map-002",
                "title": "站点地图",
                "points": [{"latitude": 31.2304, "longitude": 121.4737, "label": "站点 A"}],
                "lines": [],
            }
        )

        self.assertEqual(session.state["map_cards"][0]["id"], "map-002")
        self.assertEqual(session.state["conversation_turns"][0]["cards"][0]["id"], "map-002")
        self.assertEqual(session.state["events"][-1]["details"]["turn_id"], session.state["active_turn_id"])


if __name__ == "__main__":
    unittest.main()
