import asyncio
from app.config import get_llm_client_from_config
from app.web import WebConsoleCallback, ConsoleSession
from langchain_core.messages import HumanMessage
import time
from app.llm_streaming import extract_thinking_and_content

class MyCallback(WebConsoleCallback):
    async def on_llm_new_token(self, token: str, **kwargs) -> None:
        thinking, content = extract_thinking_and_content(kwargs.get("chunk"))
        text = content or token
        print(f"TOKEN='{token}' THINKING='{thinking}' CONTENT='{content}' TEXT='{text}'")
        await super().on_llm_new_token(token, **kwargs)

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
    
    async def reader():
        for q in session.subscribers:
            while True:
                msg = await q.get()
                # print(msg)
                
    session.subscribers.add(asyncio.Queue(maxsize=100))
    asyncio.create_task(reader())

    client = get_llm_client_from_config(config)
    messages = [HumanMessage(content="Explain what a typewriter is briefly.")]

    print("Running...")
    await client.ainvoke(messages, config)

if __name__ == "__main__":
    asyncio.run(main())
