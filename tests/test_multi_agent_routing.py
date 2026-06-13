import os
import unittest
from unittest.mock import MagicMock

os.environ.setdefault("LLM_MODEL_NAME", "gpt-4o-mini")
os.environ.setdefault("LLM_API_KEY", "dummy")
os.environ.setdefault("TAVILY_API_KEY", "dummy")

from langchain_core.messages import AIMessage, ToolMessage

from app.nodes.memory_manager import route_after_memory
from app.tools.registry import get_tools_for_agent_role, GENERAL_AGENT_TOOLS, NETWORK_SPECIALIST_TOOLS


class MultiAgentRoutingTests(unittest.TestCase):
    def test_tool_registry_isolation(self):
        # General agent must not have geo and visualization tools
        general_tools = get_tools_for_agent_role("general")
        general_tool_names = {t.name for t in general_tools}
        
        self.assertNotIn("geocode_address", general_tool_names)
        self.assertNotIn("reverse_geocode", general_tool_names)
        self.assertNotIn("render_map_card", general_tool_names)
        
        # Network specialist agent must have geo and visualization tools
        network_tools = get_tools_for_agent_role("network")
        network_tool_names = {t.name for t in network_tools}
        
        self.assertIn("geocode_address", network_tool_names)
        self.assertIn("reverse_geocode", network_tool_names)
        self.assertIn("render_map_card", network_tool_names)
        
    def test_route_after_memory_role_general(self):
        # When orchestrator decides agent_role is general, route to agent node
        state = {
            "messages": [AIMessage(content="hello")],
            "last_node": "orchestrator",
            "orchestrator_next": "agent",
            "agent_role": "general",
        }
        
        self.assertEqual(route_after_memory(state), "agent")

    def test_route_after_memory_role_network(self):
        # When orchestrator decides agent_role is network, route to network_specialist_agent node
        state = {
            "messages": [AIMessage(content="hello")],
            "last_node": "orchestrator",
            "orchestrator_next": "agent",
            "agent_role": "network",
        }
        
        self.assertEqual(route_after_memory(state), "network_specialist_agent")

    def test_route_after_memory_role_default(self):
        # Default agent_role is general
        state = {
            "messages": [AIMessage(content="hello")],
            "last_node": "orchestrator",
            "orchestrator_next": "agent",
        }
        
        self.assertEqual(route_after_memory(state), "agent")

    def test_post_process_serialized_messages_hydrates_map_widget(self):
        from app.web import post_process_serialized_messages
        
        # Mock session object with a stored map card
        mock_session = MagicMock()
        mock_session.state = {
            "map_cards": [
                {
                    "id": "map-123",
                    "center": {"latitude": 31.2304, "longitude": 121.4737},
                    "zoom": 12.0,
                    "points": [{"latitude": 31.2304, "longitude": 121.4737, "label": "上海仓"}]
                }
            ]
        }
        
        # Input messages containing a map widget placeholder
        input_messages = [
            {
                "role": "assistant",
                "content": "这里是地图：\n```widget\n{\n  \"widget_type\": \"map\",\n  \"id\": \"map-123\",\n  \"props\": {\n    \"use_stored_card\": true\n  }\n}\n```",
                "blocks": [
                    {"type": "text", "format": "markdown", "content": "这里是地图："},
                    {"type": "widget", "widget_type": "map", "id": "map-123", "props": {"use_stored_card": True}}
                ]
            }
        ]
        
        output_messages = post_process_serialized_messages(input_messages, mock_session)
        
        # Verify the map widget block's props have been hydrated/filled with the full coordinates list
        map_block = output_messages[0]["blocks"][1]
        self.assertEqual(map_block["props"]["center"]["lat"], 31.2304)
        self.assertEqual(map_block["props"]["center"]["lng"], 121.4737)
        self.assertEqual(map_block["props"]["zoom"], 12.0)
        self.assertEqual(map_block["props"]["markers"][0]["label"], "上海仓")


if __name__ == "__main__":
    unittest.main()
