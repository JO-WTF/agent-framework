import asyncio
import time
from app.config import get_llm_client_from_config
from app.web import WebConsoleCallback, ConsoleSession
from langchain_core.messages import HumanMessage
from app.cli import build_agent_graph

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
    app = build_agent_graph()
    messages = [HumanMessage(content="Explain what a typewriter is briefly in 3 sentences.")]
    initial_input = {
        "messages": messages,
        "revision_count": 0,
        "eval_status": "",
        "session_id": "test-session",
        "task_complexity": "unknown",
        "todo_list": [],
        "context_tags": ["general"],
        "world_state": {},
        "orchestrator_next": "agent",
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
                
    session.subscribers.add(asyncio.Queue(maxsize=100))
    asyncio.create_task(reader())

    print("Running graph...")
    async for update in app.astream(initial_input, config, stream_mode="updates"):
        pass

    print(f"\nDone! Received {stream_count} stream chunks.")

if __name__ == "__main__":
    asyncio.run(main())
