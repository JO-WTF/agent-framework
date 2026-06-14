import asyncio
from app.config import get_llm_client_from_config
from app.web import WebConsoleCallback, ConsoleSession
from langchain_core.messages import HumanMessage
import time
from langchain_core.tools import tool

@tool
def dummy_tool() -> str:
    "A dummy tool"
    return "ok"

class MyCallback(WebConsoleCallback):
    async def on_llm_new_token(self, token: str, **kwargs) -> None:
        print(f"[{time.time()}] TOKEN RECEIVED")

async def main():
    session = ConsoleSession("test-session")
    session.model_config_raw = None
    config = {
        "configurable": {
            "thread_id": "123",
            "session_id": "test-session",
            "llm_settings": {},
        },
        "callbacks": [MyCallback(session)],
    }
    
    client = get_llm_client_from_config(config).bind_tools([dummy_tool])
    messages = [HumanMessage(content="Count to 10 slowly. Think about it briefly.")]

    print("Running...")
    await client.ainvoke(messages, config)
    print("Done")

if __name__ == "__main__":
    asyncio.run(main())
