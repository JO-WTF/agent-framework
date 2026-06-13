import json

with open("/Users/zhaoyu/Documents/agent-framework/app/tools/geo.py", "r", encoding="utf-8") as f:
    content = f.read()

old_code = """            geojson = geojson_resp.json()
            features = geojson.get("features", [])
            region_names = sorted(set(
                f.get("properties", {}).get("shapeName") for f in features if f.get("properties", {}).get("shapeName")
            ))
            
            result_text = f"【{country_code} ADM{level} 行政区列表】共 {len(region_names)} 个:\\n" + ", ".join(region_names)
            return result_text"""

new_code = """            geojson = geojson_resp.json()
            features = geojson.get("features", [])
            region_names = sorted(set(
                f.get("properties", {}).get("shapeName") for f in features if f.get("properties", {}).get("shapeName")
            ))
            
            geojson_str = json.dumps(geojson, ensure_ascii=False)
            ref_id = store_tool_result_for_current_session("get_administrative_regions", geojson_str, {"type": "geojson"})
            
            result_text = f"【{country_code} ADM{level} 行政区列表】共 {len(region_names)} 个:\\n" + ", ".join(region_names)
            result_text += f"\\n\\n💡 提示：上述所有行政区的完整边界集合数据 (GeoJSON, 大小: {len(geojson_str)} 字节) 已存入后台引用。你可以直接使用宏语法 {{{{ref:{ref_id}}}}} 作为 geojson 参数的值传给 map_card 等工具，从而一次性展示全部行政区！"
            return result_text"""

if old_code in content:
    content = content.replace(old_code, new_code)
    with open("/Users/zhaoyu/Documents/agent-framework/app/tools/geo.py", "w", encoding="utf-8") as f:
        f.write(content)
    print("Patched geo.py successfully.")
else:
    print("Failed to find old code in geo.py.")
