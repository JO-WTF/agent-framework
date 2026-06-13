from collections.abc import Iterable

from app.tools.api_request import api_request
from app.tools.command_runner import run_command
from app.tools.context import get_session_id, set_session_id
from app.tools.geocoding import geocode_address, reverse_geocode
from app.tools.geo import get_administrative_regions, get_administrative_boundary, calculate_geodesic_distance, get_route_directions, find_nearby_pois, get_elevation
from app.tools.map_card import render_map_card
from app.tools.python_runner import run_python
from app.tools.sandbox_tools import add_shared_mount_tool, apply_sandbox_file, sandbox_status, start_sandbox, stop_sandbox
from app.tools.search import search_web
from app.tools.skills import save_skill_sop, list_skills, delete_skill_sop, get_skill_sop
from app.tools.tool_results import list_tool_results, read_tool_result, store_data
from app.tools.webpage_reader import read_webpage


TOOL_CATEGORIES = {
    "search": [search_web, read_webpage, api_request],
    "sandbox": [start_sandbox, sandbox_status, stop_sandbox, add_shared_mount_tool, apply_sandbox_file],
    "results": [list_tool_results, read_tool_result, store_data],
    "execution": [run_python, run_command],
    "skills": [save_skill_sop, list_skills, delete_skill_sop, get_skill_sop],
    "geo": [geocode_address, reverse_geocode, get_administrative_regions, get_administrative_boundary, calculate_geodesic_distance, get_route_directions, find_nearby_pois, get_elevation],
    "visualization": [render_map_card],
}

GENERAL_AGENT_TOOL_CATEGORIES = ("search", "sandbox", "results", "execution", "skills")
NETWORK_SPECIALIST_TOOL_CATEGORIES = (*GENERAL_AGENT_TOOL_CATEGORIES, "geo", "visualization")


def _dedupe_tools(tools: Iterable) -> list:
    seen: set[str] = set()
    result = []
    for tool in tools:
        name = getattr(tool, "name", repr(tool))
        if name in seen:
            continue
        seen.add(name)
        result.append(tool)
    return result


def tools_for_categories(categories: Iterable[str]) -> list:
    selected = []
    for category in categories:
        selected.extend(TOOL_CATEGORIES.get(category, []))
    return _dedupe_tools(selected)


GENERAL_AGENT_TOOLS = tools_for_categories(GENERAL_AGENT_TOOL_CATEGORIES)
NETWORK_SPECIALIST_TOOLS = tools_for_categories(NETWORK_SPECIALIST_TOOL_CATEGORIES)
AGENT_TOOLS = _dedupe_tools(tool for tools in TOOL_CATEGORIES.values() for tool in tools)
TOOL_CATEGORY_BY_NAME = {
    getattr(tool, "name", ""): category
    for category, tools in TOOL_CATEGORIES.items()
    for tool in tools
}


def get_tools_for_agent_role(agent_role: str | None) -> list:
    if agent_role == "network":
        return NETWORK_SPECIALIST_TOOLS
    return GENERAL_AGENT_TOOLS
