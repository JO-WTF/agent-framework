import json
import uuid
from datetime import datetime
from typing import Any

from langchain_core.runnables.config import RunnableConfig
from langchain_core.tools import tool

from app.config import PROMPTS
from app.logging_config import logger
from app.tools.context import get_session_id_from_config_or_context
from app.tools.storage import store_tool_result_for_current_session

MAX_MAP_POINTS = 500
MAX_MAP_LINE_COORDINATES = 2000
DEFAULT_POINT_COLOR = "#2563eb"
DEFAULT_LINE_COLOR = "#f97316"


def _as_float(value: Any, field_name: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} 必须是数字。") from exc


def _validate_lat_lng(latitude: Any, longitude: Any) -> tuple[float, float]:
    lat = _as_float(latitude, "latitude")
    lng = _as_float(longitude, "longitude")
    if not -90 <= lat <= 90:
        raise ValueError("latitude 必须在 -90 到 90 之间。")
    if not -180 <= lng <= 180:
        raise ValueError("longitude 必须在 -180 到 180 之间。")
    return lat, lng


def _normalize_point(raw: dict[str, Any], index: int) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError(f"points[{index}] 必须是对象。")
    latitude = raw.get("latitude", raw.get("lat"))
    longitude = raw.get("longitude", raw.get("lng", raw.get("lon")))
    lat, lng = _validate_lat_lng(latitude, longitude)
    return {
        "id": str(raw.get("id") or f"point-{index + 1}"),
        "latitude": lat,
        "longitude": lng,
        "label": str(raw.get("label") or raw.get("name") or f"点 {index + 1}"),
        "description": str(raw.get("description") or raw.get("address") or ""),
        "color": str(raw.get("color") or DEFAULT_POINT_COLOR),
    }


def _normalize_coordinate(raw: Any, line_index: int, coord_index: int) -> list[float]:
    if isinstance(raw, dict):
        lat, lng = _validate_lat_lng(raw.get("latitude", raw.get("lat")), raw.get("longitude", raw.get("lng", raw.get("lon"))))
        return [lng, lat]
    if isinstance(raw, (list, tuple)) and len(raw) >= 2:
        # Mapbox/GeoJSON convention is [longitude, latitude].
        lng = _as_float(raw[0], f"lines[{line_index}].coordinates[{coord_index}][0]")
        lat = _as_float(raw[1], f"lines[{line_index}].coordinates[{coord_index}][1]")
        _validate_lat_lng(lat, lng)
        return [lng, lat]
    raise ValueError(f"lines[{line_index}].coordinates[{coord_index}] 必须是 [longitude, latitude] 或包含 latitude/longitude 的对象。")


def _normalize_line(raw: dict[str, Any], index: int) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError(f"lines[{index}] 必须是对象。")
    coordinates = raw.get("coordinates") or raw.get("path") or []
    if not isinstance(coordinates, list) or len(coordinates) < 2:
        raise ValueError(f"lines[{index}].coordinates 至少需要两个坐标点。")
    if len(coordinates) > MAX_MAP_LINE_COORDINATES:
        raise ValueError(f"lines[{index}].coordinates 超过上限 {MAX_MAP_LINE_COORDINATES}。")
    return {
        "id": str(raw.get("id") or f"line-{index + 1}"),
        "label": str(raw.get("label") or raw.get("name") or f"线路 {index + 1}"),
        "color": str(raw.get("color") or DEFAULT_LINE_COLOR),
        "coordinates": [_normalize_coordinate(coord, index, coord_index) for coord_index, coord in enumerate(coordinates)],
    }


def _normalize_center(raw: dict[str, Any] | None, points: list[dict[str, Any]], lines: list[dict[str, Any]]) -> dict[str, float] | None:
    if raw:
        if not isinstance(raw, dict):
            raise ValueError("center 必须是对象。")
        lat, lng = _validate_lat_lng(raw.get("latitude", raw.get("lat")), raw.get("longitude", raw.get("lng", raw.get("lon"))))
        return {"latitude": lat, "longitude": lng}

    latitudes = [point["latitude"] for point in points]
    longitudes = [point["longitude"] for point in points]
    for line in lines:
        for lng, lat in line.get("coordinates", []):
            latitudes.append(lat)
            longitudes.append(lng)
    if not latitudes or not longitudes:
        return None
    return {"latitude": sum(latitudes) / len(latitudes), "longitude": sum(longitudes) / len(longitudes)}


def _normalize_zoom(zoom: float | int | None) -> float | None:
    if zoom is None:
        return None
    parsed = _as_float(zoom, "zoom")
    if not 0 <= parsed <= 22:
        raise ValueError("zoom 必须在 0 到 22 之间。")
    return parsed


def build_map_card_payload(
    title: str,
    points: list[dict[str, Any]] | None = None,
    lines: list[dict[str, Any]] | None = None,
    center: dict[str, Any] | None = None,
    zoom: float | int | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    normalized_points = [_normalize_point(point, idx) for idx, point in enumerate(points or [])]
    if len(normalized_points) > MAX_MAP_POINTS:
        raise ValueError(f"points 超过上限 {MAX_MAP_POINTS}。")
    normalized_lines = [_normalize_line(line, idx) for idx, line in enumerate(lines or [])]
    if not normalized_points and not normalized_lines:
        raise ValueError("地图卡片至少需要一个点或一条线。")

    return {
        "id": f"map-{uuid.uuid4().hex[:12]}",
        "title": (title or "地图展示").strip() or "地图展示",
        "note": (note or "").strip(),
        "points": normalized_points,
        "lines": normalized_lines,
        "center": _normalize_center(center, normalized_points, normalized_lines),
        "zoom": _normalize_zoom(zoom),
        "created_at": datetime.now().isoformat(),
    }


async def _publish_map_card_to_web_session(session_id: str | None, card: dict[str, Any]) -> None:
    if not session_id:
        return
    try:
        from app.web import manager
    except Exception:
        return
    session = manager.sessions.get(session_id)
    if not session:
        return
    await session.add_map_card(card)


@tool(description=PROMPTS["tools"]["render_map_card"])
async def render_map_card(
    title: str,
    points: list[dict[str, Any]] | None = None,
    lines: list[dict[str, Any]] | None = None,
    center: dict[str, Any] | None = None,
    zoom: float | None = None,
    note: str | None = None,
    config: RunnableConfig = None,
) -> str:
    session_id = get_session_id_from_config_or_context(config)
    logger.info(f"🗺️ \033[94m[触发工具: 地图卡片] -> {title}\033[0m")

    try:
        card = build_map_card_payload(title=title, points=points, lines=lines, center=center, zoom=zoom, note=note)
    except Exception as exc:
        text = f"执行失败: 地图卡片参数无效: {exc}"
        store_tool_result_for_current_session("render_map_card", text, {"status": "invalid_args", "title": title})
        return text

    # Build a lightweight widget payload to return to the agent (minimizing token footprint)
    widget_payload = {
        "widget_type": "map",
        "id": card["id"],
        "props": {
            "use_stored_card": True
        }
    }
    widget_code = f"```widget\n{json.dumps(widget_payload, ensure_ascii=False, indent=2)}\n```"

    # Store full card payload in session state for backend hydration
    await _publish_map_card_to_web_session(session_id, card)

    store_tool_result_for_current_session(
        "render_map_card",
        widget_code,
        {
            "status": "success",
            "map_card_id": card["id"],
            "point_count": len(card["points"]),
            "line_count": len(card["lines"]),
        },
    )
    return widget_code
