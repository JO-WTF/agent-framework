import json
import urllib.parse
from typing import Any

import httpx
from geopy.distance import geodesic
from langchain_core.runnables.config import RunnableConfig
from langchain_core.tools import tool

from app.logging_config import logger
from app.memory.store import save_agent_note
from app.tools.context import get_session_id_from_config_or_context
from app.tools.storage import store_tool_result_for_current_session

@tool
async def get_administrative_regions(country_code: str, level: str = "1") -> str:
    """获取行政区划列表。
    通过 geoBoundaries API 获取指定国家和指定层级的行政区列表。
    参数:
    - country_code (str): ISO 3166-1 alpha-3 国家代码 (例如 "CHN" 表示中国, "USA" 表示美国)。
    - level (str): 层级，可选值 "0" (国家级), "1" (省级/州级), "2" (市级)。默认为 "1"。
    """
    url = f"https://www.geoboundaries.org/api/current/gbOpen/{country_code}/ADM{level}/"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            if response.status_code != 200:
                return f"获取失败: HTTP {response.status_code} - 可能是国家代码或层级不支持。"
            data = response.json()
            
            # GeoBoundaries API meta endpoint usually provides a download URL for the geojson.
            simplified_url = data.get("simplifiedGeometryGeoJSON")
            if not simplified_url:
                return "获取失败: 无法找到边界数据下载链接。"
            
            geojson_resp = await client.get(simplified_url)
            if geojson_resp.status_code != 200:
                return "获取失败: 下载行政区数据失败。"
            
            geojson = geojson_resp.json()
            features = geojson.get("features", [])
            region_names = sorted(set(
                f.get("properties", {}).get("shapeName") for f in features if f.get("properties", {}).get("shapeName")
            ))
            
            result_text = f"【{country_code} ADM{level} 行政区列表】共 {len(region_names)} 个:\n" + ", ".join(region_names)
            return result_text
    except Exception as e:
        logger.error(f"get_administrative_regions error: {e}")
        return f"执行失败: {e}"

@tool
async def get_administrative_boundary(country_code: str, region_name: str, level: str = "1") -> str:
    """获取特定行政区的多边形边界数据 (GeoJSON)。
    参数:
    - country_code (str): ISO 3166-1 alpha-3 国家代码。
    - region_name (str): 行政区名称 (需与 get_administrative_regions 返回的名称一致，例如 "Shenzhen")。
    - level (str): 层级，默认为 "1" (省级/州级), "2" (市级)。
    """
    url = f"https://www.geoboundaries.org/api/current/gbOpen/{country_code}/ADM{level}/"
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(url)
            if response.status_code != 200:
                return f"获取失败: HTTP {response.status_code}。"
            
            simplified_url = response.json().get("simplifiedGeometryGeoJSON")
            if not simplified_url:
                return "获取失败: 无法找到边界数据下载链接。"
            
            geojson_resp = await client.get(simplified_url)
            if geojson_resp.status_code != 200:
                return "获取失败: 下载行政区数据失败。"
            
            features = geojson_resp.json().get("features", [])
            for f in features:
                shape_name = f.get("properties", {}).get("shapeName", "")
                if region_name.lower() in shape_name.lower():
                    result_geojson = {
                        "type": "FeatureCollection",
                        "features": [f]
                    }
                    geojson_str = json.dumps(result_geojson, ensure_ascii=False)
                    return f"成功提取 {shape_name} 的边界数据。数据格式为 GeoJSON (大小: {len(geojson_str)} 字节)。可以直接传给 map_card。\nGeoJSON截取: {geojson_str[:200]}..."
            
            return f"未找到名为 '{region_name}' 的行政区。请先调用 get_administrative_regions 确认确切名称。"
    except Exception as e:
        logger.error(f"get_administrative_boundary error: {e}")
        return f"执行失败: {e}"

@tool
def calculate_geodesic_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> str:
    """计算地球表面两点之间的最短直线距离（测地线距离）。
    参数:
    - lat1, lon1: 起点纬度、经度。
    - lat2, lon2: 终点纬度、经度。
    返回距离的公里(km)和英里(miles)。
    """
    try:
        dist = geodesic((lat1, lon1), (lat2, lon2))
        return f"两点之间的直线距离为: {dist.kilometers:.2f} 公里 ({dist.miles:.2f} 英里)。"
    except Exception as e:
        return f"计算距离失败: {e}"

@tool
async def get_route_directions(start_lat: float, start_lon: float, end_lat: float, end_lon: float, profile: str = "driving") -> str:
    """使用 OSRM API 获取导航路线、驾驶距离和预计耗时。
    参数:
    - start_lat, start_lon: 起点纬度和经度。
    - end_lat, end_lon: 终点纬度和经度。
    - profile: 出行方式，可选 "driving" (驾车), "walking" (步行), "cycling" (骑行)。
    返回路线摘要、耗时以及路径点集合 (Polyline / GeoJSON)。
    """
    if profile not in {"driving", "walking", "cycling"}:
        return "出行方式必须是 driving, walking 或 cycling。"
    
    url = f"http://router.project-osrm.org/route/v1/{profile}/{start_lon},{start_lat};{end_lon},{end_lat}?overview=simplified&geometries=geojson"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            if response.status_code != 200:
                return f"路线规划失败: OSRM 返回 {response.status_code}"
            
            data = response.json()
            if data.get("code") != "Ok" or not data.get("routes"):
                return "路线规划失败: 找不到有效路线。"
            
            route = data["routes"][0]
            distance_km = route.get("distance", 0) / 1000.0
            duration_min = route.get("duration", 0) / 60.0
            geometry = route.get("geometry")
            
            geojson = {
                "type": "FeatureCollection",
                "features": [{
                    "type": "Feature",
                    "geometry": geometry,
                    "properties": {
                        "distance_km": round(distance_km, 2),
                        "duration_min": round(duration_min, 2)
                    }
                }]
            }
            geojson_str = json.dumps(geojson, ensure_ascii=False)
            
            return f"【导航成功】方式: {profile}\n导航距离: {distance_km:.2f} 公里\n预计耗时: {duration_min:.1f} 分钟。\n路线的 GeoJSON 轨迹数据已生成，可传给 map_card 显示轨迹。\nGeoJSON截取: {geojson_str[:200]}..."
    except Exception as e:
        logger.error(f"get_route_directions error: {e}")
        return f"执行失败: {e}"

@tool
async def find_nearby_pois(lat: float, lon: float, radius: int, poi_type: str = "hospital") -> str:
    """使用 OpenStreetMap Overpass API 查找周边特定类型的兴趣点 (POI)。
    参数:
    - lat, lon: 中心点纬度、经度。
    - radius: 搜索半径 (米)，最大建议 5000。
    - poi_type: 设施类型，可以是 OSM 的 amenity 值 (如 "hospital", "cafe", "restaurant", "school") 或是模糊的设施名。
    返回搜索到的兴趣点名称及其经纬度。
    """
    if radius > 10000:
        return "半径过大，为避免 API 超时，请使用小于 10000 米的半径。"
    
    query = f"""
    [out:json][timeout:25];
    (
      node["amenity"="{poi_type}"](around:{radius},{lat},{lon});
      node["name"~"{poi_type}",i](around:{radius},{lat},{lon});
    );
    out body 20;
    """
    url = "https://overpass-api.de/api/interpreter"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, data={"data": query})
            if response.status_code != 200:
                return f"API 错误: {response.status_code}"
            
            data = response.json()
            elements = data.get("elements", [])
            if not elements:
                return f"在 {radius} 米范围内没有找到类型为 '{poi_type}' 的兴趣点。"
            
            results = []
            for el in elements:
                name = el.get("tags", {}).get("name", "未命名")
                elat, elon = el.get("lat"), el.get("lon")
                results.append(f"- {name} (Lat: {elat}, Lon: {elon})")
            
            return f"【周边搜索结果】共找到 {len(results)} 个匹配项 (最多显示20个):\n" + "\n".join(results)
    except Exception as e:
        logger.error(f"find_nearby_pois error: {e}")
        return f"执行失败: {e}"

@tool
async def get_elevation(lat: float, lon: float) -> str:
    """获取指定经纬度的地形海拔高度（高程）。
    基于 Open-Elevation API (返回单位: 米)。
    参数:
    - lat, lon: 纬度、经度。
    """
    url = f"https://api.open-elevation.com/api/v1/lookup?locations={lat},{lon}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            if response.status_code != 200:
                return f"高程获取失败: {response.status_code}"
            
            data = response.json()
            results = data.get("results", [])
            if not results:
                return "未找到高程数据。"
            
            elevation = results[0].get("elevation")
            return f"该位置的海拔高度为: {elevation} 米。"
    except Exception as e:
        logger.error(f"get_elevation error: {e}")
        return f"执行失败: {e}"
