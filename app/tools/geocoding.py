import json
import os
from typing import Any

import httpx
from langchain_core.runnables.config import RunnableConfig
from langchain_core.tools import tool

from app.config import PROMPTS
from app.logging_config import logger
from app.memory.store import save_agent_note, summarize_text
from app.tools.context import get_session_id_from_config_or_context
from app.tools.storage import store_tool_result_for_current_session

MAPBOX_FORWARD_URL = "https://api.mapbox.com/search/geocode/v6/forward"
MAPBOX_REVERSE_URL = "https://api.mapbox.com/search/geocode/v6/reverse"
HERE_FORWARD_URL = "https://geocode.search.hereapi.com/v1/geocode"
HERE_REVERSE_URL = "https://revgeocode.search.hereapi.com/v1/revgeocode"
MAX_GEOCODING_RESULTS = 10
MAX_INLINE_RESULT_CHARS = 3000


def _select_provider(provider: str) -> tuple[str | None, str | None]:
    normalized = (provider or "auto").strip().lower()
    if normalized not in {"auto", "mapbox", "here"}:
        return None, "provider 只能是 auto、mapbox 或 here。"

    mapbox_token = os.getenv("MAPBOX_ACCESS_TOKEN") or os.getenv("MAPBOX_API_KEY")
    here_key = os.getenv("HERE_API_KEY") or os.getenv("HERE_APIKEY")

    if normalized == "mapbox":
        if not mapbox_token:
            return None, "未配置 MAPBOX_ACCESS_TOKEN 或 MAPBOX_API_KEY。"
        return "mapbox", None
    if normalized == "here":
        if not here_key:
            return None, "未配置 HERE_API_KEY。"
        return "here", None
    if mapbox_token:
        return "mapbox", None
    if here_key:
        return "here", None
    return None, "未配置地理编码服务密钥，请设置 MAPBOX_ACCESS_TOKEN 或 HERE_API_KEY。"


def _clamp_limit(limit: int) -> int:
    try:
        parsed = int(limit)
    except (TypeError, ValueError):
        parsed = 5
    return max(1, min(parsed, MAX_GEOCODING_RESULTS))


def _metadata(provider: str | None, status: str, **extra: Any) -> dict[str, Any]:
    return {"provider": provider or "unknown", "status": status, **extra}


def _format_or_archive(tool_name: str, payload: dict[str, Any], metadata: dict[str, Any]) -> str:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    ref_id = store_tool_result_for_current_session(tool_name, text, metadata)
    if len(text) <= MAX_INLINE_RESULT_CHARS:
        return text
    summary = summarize_text(text, max_chars=800)
    return (
        f"结果内容过长，已保存为引用 {ref_id}。\n"
        f"如需完整内容，请调用 read_tool_result(ref_id=\"{ref_id}\")。\n"
        f"摘要:\n{summary}"
    )


def _error(tool_name: str, message: str, metadata: dict[str, Any]) -> str:
    text = f"执行失败: {message}"
    store_tool_result_for_current_session(tool_name, text, metadata)
    note_id = save_agent_note(text, source=tool_name, tags=["network", "api_call", "tool_error"])
    return f"{text}。已记录笔记 {note_id}。"


def _validate_coordinates(latitude: float, longitude: float) -> tuple[float | None, float | None, str | None]:
    try:
        lat = float(latitude)
        lng = float(longitude)
    except (TypeError, ValueError):
        return None, None, "latitude 和 longitude 必须是数字。"
    if not -90 <= lat <= 90:
        return None, None, "latitude 必须在 -90 到 90 之间。"
    if not -180 <= lng <= 180:
        return None, None, "longitude 必须在 -180 到 180 之间。"
    return lat, lng, None


def _mapbox_common_result(feature: dict[str, Any]) -> dict[str, Any]:
    properties = feature.get("properties") or {}
    geometry = feature.get("geometry") or {}
    coordinates = geometry.get("coordinates") or []
    longitude = coordinates[0] if len(coordinates) > 0 else (properties.get("coordinates") or {}).get("longitude")
    latitude = coordinates[1] if len(coordinates) > 1 else (properties.get("coordinates") or {}).get("latitude")
    return {
        "name": properties.get("name") or feature.get("text") or feature.get("place_name"),
        "address": properties.get("full_address") or properties.get("place_formatted") or feature.get("place_name"),
        "latitude": latitude,
        "longitude": longitude,
        "place_type": properties.get("feature_type") or feature.get("place_type"),
        "confidence": properties.get("match_code") or properties.get("accuracy"),
        "raw_id": feature.get("id") or properties.get("mapbox_id"),
    }


def _here_common_result(item: dict[str, Any]) -> dict[str, Any]:
    position = item.get("position") or {}
    address = item.get("address") or {}
    scoring = item.get("scoring") or {}
    return {
        "name": item.get("title"),
        "address": address.get("label") or item.get("title"),
        "latitude": position.get("lat"),
        "longitude": position.get("lng"),
        "place_type": item.get("resultType"),
        "confidence": scoring.get("queryScore"),
        "raw_id": item.get("id"),
    }


async def _request_json(url: str, params: dict[str, Any]) -> tuple[int, dict[str, Any], str]:
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(url, params={k: v for k, v in params.items() if v not in (None, "")})
    try:
        data = response.json()
    except Exception:
        data = {}
    return response.status_code, data, response.text


async def _mapbox_geocode(address: str, limit: int, country: str | None, language: str | None) -> dict[str, Any]:
    status_code, data, response_text = await _request_json(
        MAPBOX_FORWARD_URL,
        {
            "q": address,
            "limit": limit,
            "country": country,
            "language": language,
            "access_token": os.getenv("MAPBOX_ACCESS_TOKEN") or os.getenv("MAPBOX_API_KEY"),
        },
    )
    if status_code >= 400:
        raise RuntimeError(f"Mapbox API 返回 {status_code}: {response_text[:500]}")
    features = data.get("features") or []
    return {"provider": "mapbox", "query": address, "results": [_mapbox_common_result(feature) for feature in features]}


async def _mapbox_reverse(latitude: float, longitude: float, limit: int, language: str | None) -> dict[str, Any]:
    status_code, data, response_text = await _request_json(
        MAPBOX_REVERSE_URL,
        {
            "latitude": latitude,
            "longitude": longitude,
            "limit": limit,
            "language": language,
            "access_token": os.getenv("MAPBOX_ACCESS_TOKEN") or os.getenv("MAPBOX_API_KEY"),
        },
    )
    if status_code >= 400:
        raise RuntimeError(f"Mapbox API 返回 {status_code}: {response_text[:500]}")
    features = data.get("features") or []
    return {
        "provider": "mapbox",
        "query": {"latitude": latitude, "longitude": longitude},
        "results": [_mapbox_common_result(feature) for feature in features],
    }


async def _here_geocode(address: str, limit: int, country: str | None, language: str | None) -> dict[str, Any]:
    status_code, data, response_text = await _request_json(
        HERE_FORWARD_URL,
        {
            "q": address,
            "limit": limit,
            "lang": language,
            "in": f"countryCode:{country}" if country else None,
            "apiKey": os.getenv("HERE_API_KEY") or os.getenv("HERE_APIKEY"),
        },
    )
    if status_code >= 400:
        raise RuntimeError(f"HERE API 返回 {status_code}: {response_text[:500]}")
    items = data.get("items") or []
    return {"provider": "here", "query": address, "results": [_here_common_result(item) for item in items]}


async def _here_reverse(latitude: float, longitude: float, limit: int, language: str | None) -> dict[str, Any]:
    status_code, data, response_text = await _request_json(
        HERE_REVERSE_URL,
        {
            "at": f"{latitude},{longitude}",
            "limit": limit,
            "lang": language,
            "apiKey": os.getenv("HERE_API_KEY") or os.getenv("HERE_APIKEY"),
        },
    )
    if status_code >= 400:
        raise RuntimeError(f"HERE API 返回 {status_code}: {response_text[:500]}")
    items = data.get("items") or []
    return {
        "provider": "here",
        "query": {"latitude": latitude, "longitude": longitude},
        "results": [_here_common_result(item) for item in items],
    }


@tool(description=PROMPTS["tools"]["geocode_address"])
async def geocode_address(
    address: str,
    provider: str = "auto",
    limit: int = 5,
    country: str | None = None,
    language: str | None = None,
    config: RunnableConfig = None,
) -> str:
    get_session_id_from_config_or_context(config)
    logger.info(f"🗺️ \033[94m[触发工具: 地址编码] -> {address}\033[0m")

    cleaned_address = (address or "").strip()
    if not cleaned_address:
        return _error("geocode_address", "address 不能为空。", _metadata(None, "invalid_args"))

    selected_provider, provider_error = _select_provider(provider)
    if provider_error:
        return _error("geocode_address", provider_error, _metadata(selected_provider, "missing_config", requested_provider=provider))

    result_limit = _clamp_limit(limit)
    try:
        if selected_provider == "mapbox":
            payload = await _mapbox_geocode(cleaned_address, result_limit, country, language)
        else:
            payload = await _here_geocode(cleaned_address, result_limit, country, language)
    except Exception as exc:
        return _error(
            "geocode_address",
            str(exc),
            _metadata(selected_provider, "error", address=cleaned_address, requested_provider=provider),
        )

    return _format_or_archive(
        "geocode_address",
        payload,
        _metadata(selected_provider, "success", address=cleaned_address, result_count=len(payload.get("results", []))),
    )


@tool(description=PROMPTS["tools"]["reverse_geocode"])
async def reverse_geocode(
    latitude: float,
    longitude: float,
    provider: str = "auto",
    limit: int = 5,
    language: str | None = None,
    config: RunnableConfig = None,
) -> str:
    get_session_id_from_config_or_context(config)
    logger.info(f"🗺️ \033[94m[触发工具: 经纬度反编码] -> {latitude},{longitude}\033[0m")

    lat, lng, coordinate_error = _validate_coordinates(latitude, longitude)
    if coordinate_error:
        return _error("reverse_geocode", coordinate_error, _metadata(None, "invalid_args"))

    selected_provider, provider_error = _select_provider(provider)
    if provider_error:
        return _error("reverse_geocode", provider_error, _metadata(selected_provider, "missing_config", requested_provider=provider))

    result_limit = _clamp_limit(limit)
    try:
        if selected_provider == "mapbox":
            payload = await _mapbox_reverse(lat, lng, result_limit, language)
        else:
            payload = await _here_reverse(lat, lng, result_limit, language)
    except Exception as exc:
        return _error(
            "reverse_geocode",
            str(exc),
            _metadata(selected_provider, "error", latitude=lat, longitude=lng, requested_provider=provider),
        )

    return _format_or_archive(
        "reverse_geocode",
        payload,
        _metadata(selected_provider, "success", latitude=lat, longitude=lng, result_count=len(payload.get("results", []))),
    )
