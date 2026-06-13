import json
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("LLM_MODEL_NAME", "gpt-4o-mini")
os.environ.setdefault("LLM_API_KEY", "dummy")
os.environ.setdefault("TAVILY_API_KEY", "dummy")

from langchain_core.runnables import RunnableConfig

from app.tools.map_card import build_map_card_payload, render_map_card


class MapCardToolTests(unittest.IsolatedAsyncioTestCase):
    def test_build_map_card_payload_normalizes_points_and_lines(self):
        card = build_map_card_payload(
            title="仓库覆盖",
            points=[{"lat": 31.2304, "lng": 121.4737, "label": "上海仓"}],
            lines=[{"coordinates": [[121.4737, 31.2304], [121.5, 31.25]], "label": "配送线"}],
        )

        self.assertEqual(card["title"], "仓库覆盖")
        self.assertEqual(card["points"][0]["latitude"], 31.2304)
        self.assertEqual(card["points"][0]["longitude"], 121.4737)
        self.assertEqual(card["lines"][0]["coordinates"][0], [121.4737, 31.2304])
        self.assertIn("center", card)

    def test_build_map_card_payload_rejects_empty_card(self):
        with self.assertRaises(ValueError):
            build_map_card_payload(title="空地图", points=[], lines=[])

    @patch("app.tools.map_card._publish_map_card_to_web_session")
    @patch("app.tools.map_card.store_tool_result_for_current_session", return_value="tool-001")
    @patch("app.tools.map_card.get_session_id_from_config_or_context", return_value="test-session")
    async def test_render_map_card_returns_widget_code(self, mock_session, mock_store, mock_publish):
        config = RunnableConfig(configurable={"session_id": "test-session"})

        result = await render_map_card.ainvoke(
            {
                "title": "站点地图",
                "points": [{"latitude": 31.2304, "longitude": 121.4737, "label": "站点 A"}],
            },
            config=config,
        )

        self.assertIn("```widget", result)
        self.assertIn('"widget_type": "map"', result)
        self.assertIn('"use_stored_card": true', result)
        mock_store.assert_called_once()
        mock_publish.assert_awaited_once()
        
        published_payload = mock_publish.call_args[0][1]
        self.assertEqual(published_payload["points"][0]["label"], "站点 A")

    @patch("app.tools.map_card.store_tool_result_for_current_session", return_value="tool-002")
    @patch("app.tools.map_card.get_session_id_from_config_or_context", return_value="test-session")
    async def test_render_map_card_reports_invalid_coordinates(self, mock_session, mock_store):
        result = await render_map_card.ainvoke(
            {
                "title": "错误地图",
                "points": [{"latitude": 120, "longitude": 121.4737}],
            },
            config=RunnableConfig(configurable={"session_id": "test-session"}),
        )

        self.assertIn("执行失败: 地图卡片参数无效", result)
        self.assertIn("latitude 必须在 -90 到 90 之间", result)
        mock_store.assert_called_once()


if __name__ == "__main__":
    unittest.main()
