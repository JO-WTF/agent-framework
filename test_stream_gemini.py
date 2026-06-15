import asyncio
from app.config import get_llm_client_from_config
from app.web import WebConsoleCallback, ConsoleSession
from langchain_core.messages import HumanMessage
import time
from langchain_core.tools import tool
import os

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
    
    # We will fake the Gemini config
    config = {
        "configurable": {
            "thread_id": "123",
            "session_id": "test-session",
            "llm_settings": {
                "provider": "google",
                "model_name": "gemini-2.5-pro", # or whatever
                "temperature": 0.1,
            },
        },
        "callbacks": [MyCallback(session)],
    }
    
    # Let's see if get_llm_client_from_config supports Gemini
    try:
        client = get_llm_client_from_config(config).bind_tools([dummy_tool])
    except Exception as e:
        print("Could not initialize Gemini client:", e)
        return

    messages = [HumanMessage(content="Count to 10 slowly. Think about it briefly.")]

    print("Running...")
    try:
        await client.ainvoke(messages, config)
        print("Done")
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    asyncio.run(main())
