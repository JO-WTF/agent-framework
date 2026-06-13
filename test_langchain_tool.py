import asyncio
from langchain_core.tools import tool

class MyObject:
    pass

@tool
def my_tool() -> MyObject:
    """test tool"""
    return MyObject()

async def main():
    res = await my_tool.ainvoke({})
    print(type(res))

asyncio.run(main())
