import json
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("LLM_MODEL_NAME", "gpt-4o-mini")
os.environ.setdefault("LLM_API_KEY", "dummy")
os.environ.setdefault("TAVILY_API_KEY", "dummy")

from langchain_core.runnables import RunnableConfig

from app.tools.geocoding import geocode_address, reverse_geocode
from app.tools.registry import GENERAL_AGENT_TOOLS, NETWORK_SPECIALIST_TOOLS, TOOL_CATEGORIES, TOOL_CATEGORY_BY_NAME


class FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload, ensure_ascii=False)

    def json(self):
        return self._payload


class FakeAsyncClient:
    calls = []
    response = FakeResponse(200, {})

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url, params=None):
        self.__class__.calls.append({"url": url, "params": params or {}})
        return self.__class__.response


class GeocodingToolTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        FakeAsyncClient.calls = []
        FakeAsyncClient.response = FakeResponse(200, {})
        self.config = RunnableConfig(configurable={"session_id": "test-session"})

    @patch.dict(os.environ, {"MAPBOX_ACCESS_TOKEN": "mapbox-token"}, clear=False)
    @patch("app.tools.geocoding.httpx.AsyncClient", FakeAsyncClient)
    @patch("app.tools.geocoding.store_tool_result_for_current_session", return_value="tool-001")
    @patch("app.tools.geocoding.get_session_id_from_config_or_context")
    async def test_geocode_address_uses_mapbox_and_normalizes_results(self, mock_session, mock_store):
        FakeAsyncClient.response = FakeResponse(
            200,
            {
                "features": [
                    {
                        "id": "mapbox.1",
                        "geometry": {"coordinates": [121.4737, 31.2304]},
                        "properties": {"name": "上海市", "full_address": "中国上海市", "feature_type": "place"},
                    }
                ]
            },
        )

        result = await geocode_address.ainvoke({"address": "上海市", "provider": "mapbox"}, config=self.config)
        payload = json.loads(result)

        self.assertEqual(payload["provider"], "mapbox")
        self.assertEqual(payload["results"][0]["latitude"], 31.2304)
        self.assertEqual(payload["results"][0]["longitude"], 121.4737)
        self.assertEqual(FakeAsyncClient.calls[0]["params"]["access_token"], "mapbox-token")
        mock_store.assert_called_once()

    @patch.dict(os.environ, {"HERE_API_KEY": "here-key"}, clear=False)
    @patch("app.tools.geocoding.httpx.AsyncClient", FakeAsyncClient)
    @patch("app.tools.geocoding.store_tool_result_for_current_session", return_value="tool-002")
    @patch("app.tools.geocoding.get_session_id_from_config_or_context")
    async def test_reverse_geocode_uses_here_and_normalizes_results(self, mock_session, mock_store):
        FakeAsyncClient.response = FakeResponse(
            200,
            {
                "items": [
                    {
                        "id": "here.1",
                        "title": "上海市黄浦区",
                        "address": {"label": "中国上海市黄浦区"},
                        "position": {"lat": 31.2304, "lng": 121.4737},
                        "resultType": "locality",
                        "scoring": {"queryScore": 0.99},
                    }
                ]
            },
        )

        result = await reverse_geocode.ainvoke(
            {"latitude": 31.2304, "longitude": 121.4737, "provider": "here"},
            config=self.config,
        )
        payload = json.loads(result)

        self.assertEqual(payload["provider"], "here")
        self.assertEqual(payload["results"][0]["address"], "中国上海市黄浦区")
        self.assertEqual(FakeAsyncClient.calls[0]["params"]["apiKey"], "here-key")
        mock_store.assert_called_once()

    @patch.dict(os.environ, {"MAPBOX_ACCESS_TOKEN": "", "MAPBOX_API_KEY": "", "HERE_API_KEY": "", "HERE_APIKEY": ""}, clear=False)
    @patch("app.tools.geocoding.save_agent_note", return_value="note-001")
    @patch("app.tools.geocoding.store_tool_result_for_current_session", return_value="tool-003")
    @patch("app.tools.geocoding.get_session_id_from_config_or_context")
    async def test_geocode_address_reports_missing_provider_config(self, mock_session, mock_store, mock_note):
        result = await geocode_address.ainvoke({"address": "上海市", "provider": "auto"}, config=self.config)

        self.assertIn("执行失败", result)
        self.assertIn("未配置地理编码服务密钥", result)
        mock_store.assert_called_once()
        mock_note.assert_called_once()

    @patch("app.tools.geocoding.save_agent_note", return_value="note-002")
    @patch("app.tools.geocoding.store_tool_result_for_current_session", return_value="tool-004")
    @patch("app.tools.geocoding.get_session_id_from_config_or_context")
    async def test_reverse_geocode_validates_coordinate_ranges(self, mock_session, mock_store, mock_note):
        result = await reverse_geocode.ainvoke({"latitude": 120, "longitude": 121.4737}, config=self.config)

        self.assertIn("latitude 必须在 -90 到 90 之间", result)
        mock_store.assert_called_once()
        mock_note.assert_called_once()

    def test_tool_registry_categorizes_geo_tools_for_network_specialist(self):
        general_names = {tool.name for tool in GENERAL_AGENT_TOOLS}
        network_names = {tool.name for tool in NETWORK_SPECIALIST_TOOLS}
        geo_names = {tool.name for tool in TOOL_CATEGORIES["geo"]}
        visualization_names = {tool.name for tool in TOOL_CATEGORIES["visualization"]}

        self.assertEqual(
            geo_names,
            {
                "geocode_address",
                "reverse_geocode",
                "get_administrative_regions",
                "get_administrative_boundary",
                "calculate_geodesic_distance",
                "get_route_directions",
                "find_nearby_pois",
                "get_elevation",
            },
        )
        self.assertEqual(visualization_names, {"render_map_card"})
        self.assertIn("geocode_address", general_names)
        self.assertIn("render_map_card", general_names)
        self.assertIn("geocode_address", network_names)
        self.assertIn("render_map_card", network_names)
        self.assertEqual(TOOL_CATEGORY_BY_NAME["reverse_geocode"], "geo")
        self.assertEqual(TOOL_CATEGORY_BY_NAME["render_map_card"], "visualization")


if __name__ == "__main__":
    unittest.main()
