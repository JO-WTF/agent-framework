import asyncio
from app.tools.geo import get_administrative_regions, get_administrative_boundary

async def test():
    # 1. Get regions for Indonesia (IDN) level 1
    res = await get_administrative_regions.ainvoke({"country_code": "IDN", "level": "1"})
    print("Regions:", res)

    # 2. Get Jakarta boundary
    res2 = await get_administrative_boundary.ainvoke({"country_code": "IDN", "region_name": "Jakarta", "level": "1"})
    print("Boundary result:", res2)

if __name__ == "__main__":
    asyncio.run(test())
