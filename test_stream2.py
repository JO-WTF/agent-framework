import asyncio
import time
from app.config import get_llm_client_from_config
from app.web import WebConsoleCallback, ConsoleSession
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool

@tool
def dummy_tool() -> str:
    "A dummy tool"
    return "ok"

async def main():
    session = ConsoleSession("test-session")
    config = {
        "callbacks": [WebConsoleCallback(session)]
    }
    client = get_llm_client_from_config(config).bind_tools([dummy_tool])
    messages = [HumanMessage(content="Count to 10 slowly. Think about it briefly.")]
    
    start_time = time.time()
    async def reader():
        for q in session.subscribers:
            while True:
                msg = await q.get()
                print(f"[{time.time() - start_time:.2f}s] WS MSG:", msg.get("type"), msg.get("content", ""))
                if "state" in msg:
                    break
                
    session.subscribers.add(asyncio.Queue())
    asyncio.create_task(reader())

    response = await client.ainvoke(messages, config)

if __name__ == "__main__":
    asyncio.run(main())
