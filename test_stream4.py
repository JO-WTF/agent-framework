import asyncio
from app.config import get_llm_client_from_config
from app.web import WebConsoleCallback, ConsoleSession
from langchain_core.messages import HumanMessage
from app.nodes.agent import _run_agent_node
import time

async def main():
    session = ConsoleSession("test-session")
    session.model_config_raw = None
    config = {
        "configurable": {
            "thread_id": "123",
            "session_id": "test-session",
            "llm_settings": {},
        },
        "callbacks": [WebConsoleCallback(session)],
    }
    
    start_time = time.time()
    stream_count = 0
    async def reader():
        nonlocal stream_count
        for q in session.subscribers:
            while True:
                msg = await q.get()
                if msg.get("type") == "stream":
                    stream_count += 1
                    print(msg.get("content"), end="", flush=True)
                
    session.subscribers.add(asyncio.Queue(maxsize=100))
    asyncio.create_task(reader())

    state = {
        "messages": [HumanMessage(content="Explain what a typewriter is briefly.")],
        "session_id": "test-session",
        "context_tags": ["general"],
        "todo_list": [],
        "world_state": {},
        "events": [],
    }

    print("Running node...")
    await _run_agent_node(
        state, config,
        prompt_key="agent_general",
        node_name="agent",
        log_label="Agent Brain"
    )

    print(f"\nDone! Received {stream_count} stream chunks.")

if __name__ == "__main__":
    asyncio.run(main())
