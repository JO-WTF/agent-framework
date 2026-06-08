import asyncio
import json
import re
import uuid
from datetime import datetime
from typing import Any

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from pydantic import BaseModel

from app.cli import build_agent_graph
from app.memory.store import append_session_event, trim_messages
from app.runtime_paths import STATIC_DIR


class ChatRequest(BaseModel):
    message: str


def parse_thinking_content(content: str) -> tuple[str, str]:
    think = ""
    message = content
    think_start = content.find("<think>")
    if think_start != -1:
        think_end = content.find("</think>", think_start + 7)
        if think_end != -1:
            think = content[think_start + 7 : think_end].strip()
            message = (content[:think_start] + content[think_end + 8 :]).strip()
        else:
            think = content[think_start + 7 :].strip()
            message = content[:think_start].strip()
    return think, message


class ConsoleSession:
    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self.agent_app = build_agent_graph()
        self.thread_id = str(uuid.uuid4())
        self.memory_messages = []
        self.running_task: asyncio.Task | None = None
        self.subscribers: set[asyncio.Queue] = set()
        self.state: dict[str, Any] = {
            "status": "idle",
            "current_node": "",
            "task_complexity": "unknown",
            "todo_list": [],
            "model_output": "",
            "tool_runs": [],
            "events": [],
            "messages": [],
        }

    def snapshot(self) -> dict[str, Any]:
        return self.state

    async def publish(self, event: dict[str, Any]) -> None:
        event = {
            "id": str(uuid.uuid4()),
            "time": datetime.now().strftime("%H:%M:%S"),
            "updated_at": "",
            "details": {},
            **event,
        }
        self.state["events"].append(event)
        self.state["events"] = self.state["events"][-200:]
        append_session_event(self.session_id, event)
        await self.broadcast(event)

    async def start_node_llm_run(self, node_name: str, prompts: list[str]) -> None:
        now = datetime.now().strftime("%H:%M:%S")
        formatted_prompts = []
        for p in prompts:
            if isinstance(p, str):
                formatted_prompts.append({"role": "prompt", "content": p})
            else:
                formatted_prompts.append({"role": "prompt", "content": str(p)})

        event = {
            "id": str(uuid.uuid4()),
            "time": now,
            "updated_at": "",
            "type": "node_update",
            "title": f"节点更新: {node_name} (模型调用中...)",
            "node": node_name,
            "details": {
                "node": node_name,
                "update": {},
                "llm_run": {
                    "prompts": formatted_prompts,
                    "content": "",
                    "think": "",
                    "message": "",
                    "token_count": 0,
                    "status": "running",
                }
            },
        }
        self.state["events"].append(event)
        self.state["events"] = self.state["events"][-200:]
        append_session_event(self.session_id, event)
        await self.broadcast(event)

    async def update_node_llm_run(self, token: str) -> None:
        now = datetime.now().strftime("%H:%M:%S")
        events = self.state["events"]
        last_event = events[-1] if events else None

        if last_event and last_event.get("type") == "node_update" and last_event.get("node") == "agent":
            details = last_event.setdefault("details", {})
            llm_run = details.setdefault("llm_run", {})
            content = f"{llm_run.get('content', '')}{token}"
            llm_run["content"] = content
            llm_run["token_count"] = llm_run.get("token_count", 0) + 1

            # Parse think and message
            think, message = parse_thinking_content(content)
            llm_run["think"] = think
            llm_run["message"] = message

            last_event["title"] = f"节点更新: agent (正在调用模型, {llm_run['token_count']} tokens)"
            last_event["updated_at"] = now
            await self.broadcast(last_event)

    async def complete_node_llm_run(self) -> None:
        now = datetime.now().strftime("%H:%M:%S")
        events = self.state["events"]
        last_event = events[-1] if events else None

        if last_event and last_event.get("type") == "node_update" and last_event.get("node") == "agent":
            details = last_event.setdefault("details", {})
            llm_run = details.setdefault("llm_run", {})
            llm_run["status"] = "completed"
            last_event["title"] = f"节点更新: agent (模型调用完成, {llm_run.get('token_count', 0)} tokens)"
            last_event["updated_at"] = now
            await self.broadcast(last_event)



    async def broadcast(self, event: dict[str, Any]) -> None:
        stale = []
        for queue in self.subscribers:
            try:
                queue.put_nowait({"event": event, "state": self.snapshot()})
            except asyncio.QueueFull:
                stale.append(queue)
        for queue in stale:
            self.subscribers.discard(queue)

    def clear(self) -> None:
        if self.running_task and not self.running_task.done():
            self.running_task.cancel()
        self.thread_id = str(uuid.uuid4())
        self.memory_messages = []
        self.running_task = None
        self.state.update({
            "status": "idle",
            "current_node": "",
            "task_complexity": "unknown",
            "todo_list": [],
            "model_output": "",
            "tool_runs": [],
            "events": [],
            "messages": [],
        })


class SessionManager:
    def __init__(self) -> None:
        self.sessions: dict[str, ConsoleSession] = {}

    def create_session(self, session_id: str | None = None) -> tuple[str, ConsoleSession]:
        session_id = session_id or str(uuid.uuid4())
        session = ConsoleSession(session_id)
        self.sessions[session_id] = session
        return session_id, session

    def get_session(self, session_id: str | None) -> tuple[str, ConsoleSession]:
        if session_id:
            if session_id in self.sessions:
                return session_id, self.sessions[session_id]
            return self.create_session(session_id)
        return self.create_session()

    def remove_session(self, session_id: str) -> None:
        self.sessions.pop(session_id, None)


manager = SessionManager()
app = FastAPI(title="Agent Console")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class WebConsoleCallback(AsyncCallbackHandler):
    def __init__(self, session: ConsoleSession) -> None:
        self.session = session

    async def on_llm_start(self, serialized, prompts, **kwargs):
        self.session.state["current_node"] = "agent"
        if self.session.state["model_output"]:
            self.session.state["model_output"] += "\n\n--- [下一轮模型输出] ---\n\n"
        await self.session.start_node_llm_run("agent", prompts)

    async def on_llm_new_token(self, token: str, **kwargs) -> None:
        if not token:
            return
        self.session.state["model_output"] += token
        await self.session.update_node_llm_run(token)

    async def on_llm_end(self, response, **kwargs):
        await self.session.complete_node_llm_run()



    async def on_tool_start(self, serialized, input_str, **kwargs):
        name = serialized.get("name", "unknown_tool") if isinstance(serialized, dict) else "unknown_tool"
        run = {
            "id": str(uuid.uuid4()),
            "name": name,
            "status": "running",
            "input": input_str,
            "output": "",
            "started_at": datetime.now().strftime("%H:%M:%S"),
            "ended_at": "",
        }
        self.session.state["tool_runs"].append(run)
        self.session.state["current_node"] = "tools"
        await self.session.publish({
            "type": "tool_start",
            "title": f"调用工具: {name} (运行中...)",
            "tool": run,
            "details": {"tool": name, "input": input_str, "status": "running"},
        })

    async def on_tool_end(self, output, **kwargs):
        if self.session.state["tool_runs"]:
            run = self.session.state["tool_runs"][-1]
            output_content = getattr(output, "content", str(output))
            run["status"] = "success"
            run["output"] = output_content
            run["ended_at"] = datetime.now().strftime("%H:%M:%S")

            events = self.session.state["events"]
            last_event = None
            for e in reversed(events):
                if e.get("type") == "tool_start" and e.get("details", {}).get("tool") == run["name"]:
                    last_event = e
                    break

            if last_event:
                last_event["type"] = "tool_end"
                last_event["title"] = f"工具完成: {run['name']}"
                last_event["updated_at"] = run["ended_at"]
                last_event["tool"] = run
                last_event["details"] = {
                    "tool": run["name"],
                    "input": run["input"],
                    "output": run["output"],
                    "status": "success",
                }
                append_session_event(self.session.session_id, last_event)
                await self.session.broadcast(last_event)
            else:
                await self.session.publish({
                    "type": "tool_end",
                    "title": f"工具完成: {run['name']}",
                    "tool": run,
                    "details": {"tool": run["name"], "input": run["input"], "output": run["output"], "status": "success"},
                })

    async def on_tool_error(self, error, **kwargs):
        if self.session.state["tool_runs"]:
            run = self.session.state["tool_runs"][-1]
            run["status"] = "error"
            run["output"] = str(error)
            run["ended_at"] = datetime.now().strftime("%H:%M:%S")

            events = self.session.state["events"]
            last_event = None
            for e in reversed(events):
                if e.get("type") == "tool_start" and e.get("details", {}).get("tool") == run["name"]:
                    last_event = e
                    break

            if last_event:
                last_event["type"] = "tool_error"
                last_event["title"] = f"工具失败: {run['name']}"
                last_event["updated_at"] = run["ended_at"]
                last_event["tool"] = run
                last_event["details"] = {
                    "tool": run["name"],
                    "input": run["input"],
                    "error": run["output"],
                    "status": "error",
                }
                append_session_event(self.session.session_id, last_event)
                await self.session.broadcast(last_event)
            else:
                await self.session.publish({
                    "type": "tool_error",
                    "title": f"工具失败: {run['name']}",
                    "tool": run,
                    "details": {"tool": run["name"], "input": run["input"], "error": run["output"], "status": "error"},
                })


def serialize_message(message: Any) -> dict[str, Any]:
    role = "assistant"
    if isinstance(message, HumanMessage):
        role = "user"
    elif isinstance(message, ToolMessage):
        role = "tool"

    return {
        "role": role,
        "content": getattr(message, "content", ""),
        "tool_calls": getattr(message, "tool_calls", None) or [],
    }


def make_json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): make_json_safe(val) for key, val in value.items()}
    if isinstance(value, list | tuple):
        return [make_json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (AIMessage, HumanMessage, ToolMessage)):
        return serialize_message(value)
    return str(value)


def normalized_json(value: Any) -> str:
    return json.dumps(make_json_safe(value), ensure_ascii=False, sort_keys=True)


def resolve_session(request: Request) -> tuple[str, ConsoleSession]:
    session_id = request.headers.get("X-Session-Id") or request.query_params.get("session_id")
    return manager.get_session(session_id)


async def run_agent(user_message: HumanMessage, session: ConsoleSession, session_id: str | None = None) -> None:
    session.memory_messages = trim_messages(session.memory_messages, session_id=session_id)
    initial_input = {
        "messages": session.memory_messages,
        "revision_count": 0,
        "eval_status": "",
        "session_id": session_id or "cli",
        "task_complexity": "unknown",
        "todo_list": [],
        "context_tags": ["general"],
        "world_state": {},
        "orchestrator_next": "agent",
    }
    config = {
        "configurable": {"thread_id": session.thread_id},
        "callbacks": [WebConsoleCallback(session)],
    }

    final_reply: AIMessage | None = None
    try:
        async for update in session.agent_app.astream(initial_input, config, stream_mode="updates"):
            for node_name, node_update in update.items():
                session.state["current_node"] = node_name
                events = session.state["events"]
                last_event = events[-1] if events else None

                if (last_event and last_event.get("type") == "node_update" 
                        and last_event.get("node") == node_name):
                    details = last_event.setdefault("details", {})
                    details["update"] = make_json_safe(node_update)
                    if node_name == "agent" and "llm_run" in details:
                        token_count = details["llm_run"].get("token_count", 0)
                        last_event["title"] = f"节点更新: agent (模型调用完成, {token_count} tokens)"
                    else:
                        last_event["title"] = f"节点更新: {node_name}"
                    last_event["updated_at"] = datetime.now().strftime("%H:%M:%S")
                    append_session_event(session.session_id, last_event)
                    await session.broadcast(last_event)
                else:
                    await session.publish({
                        "type": "node_update",
                        "title": f"节点更新: {node_name}",
                        "node": node_name,
                        "details": {"node": node_name, "update": make_json_safe(node_update)},
                    })


                if node_name == "orchestrator":
                    previous_todo = session.state.get("todo_list", [])
                    previous_complexity = session.state.get("task_complexity", "unknown")
                    previous_next = session.state.get("orchestrator_next", "")
                    next_todo = node_update.get("todo_list", [])
                    next_complexity = node_update.get("task_complexity", "unknown")
                    next_route = node_update.get("orchestrator_next", "")

                    session.state["task_complexity"] = node_update.get("task_complexity", "unknown")
                    session.state["todo_list"] = next_todo
                    session.state["orchestrator_next"] = next_route
                    session.state["context_tags"] = node_update.get("context_tags", session.state.get("context_tags", ["general"]))

                    todo_changed = normalized_json(previous_todo) != normalized_json(next_todo)
                    complexity_changed = previous_complexity != next_complexity
                    route_changed = previous_next != next_route

                    if todo_changed:

                        await session.publish({
                            "type": "todo_update",
                            "title": "任务计划已更新",

                            "details": {
                                "task_complexity": session.state["task_complexity"],
                                "previous_task_complexity": previous_complexity,
                                "orchestrator_next": next_route,
                                "previous_orchestrator_next": previous_next,
                                "changed": {
                                    "todo_list": todo_changed,
                                    "task_complexity": complexity_changed,
                                    "orchestrator_next": route_changed,
                                },
                                "previous_todo_list": make_json_safe(previous_todo),
                                "current_todo_list": make_json_safe(session.state["todo_list"]),
                            },
                        })

                if node_name == "memory":
                    session.state["world_state"] = node_update.get("world_state", session.state.get("world_state", {}))

                for message in node_update.get("messages", []):
                    if isinstance(message, AIMessage) and not getattr(message, "tool_calls", None):
                        final_reply = message

        if final_reply:
            session.memory_messages.append(final_reply)
            session.memory_messages = trim_messages(session.memory_messages, session_id=session_id)
            session.state["messages"] = [serialize_message(m) for m in session.memory_messages]
            await session.broadcast({"type": "messages_update", "title": "对话已更新", "details": {}})

        session.state["status"] = "idle"
        session.state["current_node"] = ""
        await session.publish({"type": "run_complete", "title": "任务完成", "details": {"status": "idle"}})
    except asyncio.CancelledError:
        if session.memory_messages and session.memory_messages[-1] is user_message:
            session.memory_messages.pop()
        session.state["status"] = "cancelled"
        session.state["current_node"] = ""
        await session.publish({"type": "run_cancelled", "title": "任务已停止", "details": {"status": "cancelled"}})
        raise
    except Exception as exc:
        if session.memory_messages and session.memory_messages[-1] is user_message:
            session.memory_messages.pop()
        session.state["status"] = "error"
        session.state["current_node"] = ""
        await session.publish({"type": "run_error", "title": "任务失败", "error": str(exc), "details": {"error": str(exc)}})
    finally:
        session.running_task = None


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/state")
async def get_state(request: Request):
    session_id, session = resolve_session(request)
    return {"session_id": session_id, **session.snapshot()}


@app.post("/api/chat")
async def chat(request: Request, payload: ChatRequest):
    session_id, session = resolve_session(request)
    message = payload.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="message is required")
    if session.running_task and not session.running_task.done():
        raise HTTPException(status_code=409, detail="agent is already running")

    user_message = HumanMessage(content=message)
    session.memory_messages.append(user_message)
    session.state.update({
        "status": "running",
        "current_node": "orchestrator",
        "task_complexity": "unknown",
        "todo_list": [],
        "context_tags": ["general"],
        "world_state": {},
        "model_output": "",
        "tool_runs": [],
        "events": [],
        "messages": [serialize_message(m) for m in session.memory_messages],
    })
    await session.publish({
        "type": "run_start",
        "title": "任务开始",
        "details": {"user_message": message, "thread_id": session.thread_id},
    })
    session.running_task = asyncio.create_task(run_agent(user_message, session, session_id))
    return {"status": "started", "session_id": session_id, "state": session.snapshot()}


@app.post("/api/stop")
async def stop(request: Request):
    _, session = resolve_session(request)
    if session.running_task and not session.running_task.done():
        session.running_task.cancel()
        return {"status": "stopping"}
    return {"status": "idle"}


@app.post("/api/clear")
async def clear(request: Request):
    _, session = resolve_session(request)
    session.clear()
    await session.publish({"type": "clear", "title": "会话已清空", "details": {"status": "idle"}})
    return {"status": "cleared"}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    session_id = websocket.query_params.get("session_id")
    session_id, session = manager.get_session(session_id)
    await websocket.accept()
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    session.subscribers.add(queue)
    await websocket.send_json({"event": {"type": "snapshot"}, "session_id": session_id, "state": session.snapshot()})
    try:
        while True:
            payload = await queue.get()
            if payload is None:
                break
            await websocket.send_json(payload)
    except asyncio.CancelledError:
        pass
    except WebSocketDisconnect:
        pass
    finally:
        session.subscribers.discard(queue)


@app.on_event("shutdown")
async def shutdown_event():
    # Cancel only our session running tasks to allow immediate uvicorn reload
    tasks = []
    for session in manager.sessions.values():
        if session.running_task and not session.running_task.done():
            session.running_task.cancel()
            tasks.append(session.running_task)
        # Feed None to all subscriber queues to unblock websocket tasks
        for q in list(session.subscribers):
            try:
                q.put_nowait(None)
            except asyncio.QueueFull:
                pass
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

# reload test comment v4





