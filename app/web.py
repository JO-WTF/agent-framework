import asyncio
import json
import os
import re
import uuid
from datetime import datetime
from typing import Any

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from pydantic import BaseModel, ConfigDict, Field

from app.cli import build_agent_graph
from app.config import get_llm_settings, normalize_llm_settings, redact_llm_settings
from app.llm_streaming import extract_thinking_and_content
from app.llm_logging import log_user_question
from app.memory.store import append_session_event, trim_messages
from app.runtime_paths import STATIC_DIR
from app.tools.approvals import approve_pending_approval, list_approvals, list_pending_approvals, reject_approval
from app.tools.sandbox import SandboxError


class ChatRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    message: str
    llm_config: dict[str, Any] | None = Field(default=None, alias="model_config")


class ApprovalDecisionRequest(BaseModel):
    approval_id: str


_THINK_BLOCK_RE = re.compile(r"<think>(.*?)</think>", re.DOTALL | re.IGNORECASE)
_OPEN_THINK_RE = re.compile(r"<think>(.*)$", re.DOTALL | re.IGNORECASE)


def parse_thinking_content(content: str) -> tuple[str, str]:
    """Split server-provided ``<think>`` blocks from final message text.

    Some OpenAI-compatible providers stream reasoning as normal content wrapped
    with ``<think>...</think>`` instead of metadata fields. During streaming the
    closing tag may not have arrived yet, so this parser also treats a trailing
    open ``<think>`` block as in-progress thinking rather than user-visible text.
    """
    if not content:
        return "", ""

    thinking_parts: list[str] = []
    message_parts: list[str] = []
    cursor = 0

    for match in _THINK_BLOCK_RE.finditer(content):
        message_parts.append(content[cursor : match.start()])
        thinking_parts.append(match.group(1))
        cursor = match.end()

    remainder = content[cursor:]
    open_match = _OPEN_THINK_RE.search(remainder)
    if open_match:
        message_parts.append(remainder[: open_match.start()])
        thinking_parts.append(open_match.group(1))
    else:
        message_parts.append(remainder)

    return "".join(thinking_parts).strip(), "".join(message_parts).strip()


class ConsoleSession:
    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self.agent_app = build_agent_graph()
        self.thread_id = str(uuid.uuid4())
        self.memory_messages = []
        self.model_config_raw: dict[str, Any] | None = None
        self.running_task: asyncio.Task | None = None
        self.subscribers: set[asyncio.Queue] = set()
        self.state: dict[str, Any] = {
            "status": "idle",
            "current_node": "",
            "task_complexity": "unknown",
            "todo_list": [],
            "context_tags": ["general"],
            "agent_role": "general",
            "model_output": "",
            "tool_runs": [],
            "events": [],
            "messages": [],
            "map_cards": [],
            "model_config": get_llm_settings(),
            "llm_active_node": None,
            "active_skills": [],
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


    async def add_map_card(self, card: dict[str, Any]) -> None:
        cards = [c for c in self.state.get("map_cards", []) if c.get("id") != card.get("id")]
        cards.append(card)
        self.state["map_cards"] = cards[-50:]
        await self.publish({
            "type": "map_card",
            "title": f"地图卡片: {card.get('title', '地图展示')}",
            "details": {"card": card},
        })

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

    async def update_node_llm_run(self, token: str, token_type: str = "content") -> None:
        now = datetime.now().strftime("%H:%M:%S")
        events = self.state["events"]
        last_event = events[-1] if events else None
        active_node = self.state.get("llm_active_node") or "agent"

        if last_event and last_event.get("type") == "node_update" and last_event.get("node") == active_node:
            details = last_event.setdefault("details", {})
            llm_run = details.setdefault("llm_run", {})

            if token_type == "thinking":
                llm_run["_thinking_field_used"] = True

            content = llm_run.get("content", "")

            if llm_run.get("_thinking_field_used"):
                last_think = content.rfind("<think>")
                last_think_close = content.rfind("</think>")
                is_think_open = (last_think != -1) and (last_think_close == -1 or last_think > last_think_close)

                if token_type == "thinking":
                    if not is_think_open:
                        content += f"<think>{token}"
                    else:
                        content += token
                else:
                    if is_think_open:
                        content += f"</think>{token}"
                    else:
                        content += token
            else:
                content += token

            llm_run["content"] = content
            llm_run["token_count"] = llm_run.get("token_count", 0) + 1

            think, message = parse_thinking_content(content)
            llm_run["think"] = think
            llm_run["message"] = message

            last_event["title"] = f"节点更新: {active_node} (正在调用模型, {llm_run['token_count']} tokens)"
            last_event["updated_at"] = now
            await self.broadcast(last_event)

    async def complete_node_llm_run(self) -> None:
        now = datetime.now().strftime("%H:%M:%S")
        events = self.state["events"]
        last_event = events[-1] if events else None
        active_node = self.state.get("llm_active_node") or "agent"

        if last_event and last_event.get("type") == "node_update" and last_event.get("node") == active_node:
            details = last_event.setdefault("details", {})
            llm_run = details.setdefault("llm_run", {})

            content = llm_run.get("content", "")
            if llm_run.get("_thinking_field_used"):
                last_think = content.rfind("<think>")
                last_think_close = content.rfind("</think>")
                is_think_open = (last_think != -1) and (last_think_close == -1 or last_think > last_think_close)
                if is_think_open:
                    content += "</think>"
                    llm_run["content"] = content

            think, message = parse_thinking_content(content)
            llm_run["think"] = think
            llm_run["message"] = message

            llm_run["status"] = "completed"
            last_event["title"] = f"节点更新: {active_node} (模型调用完成, {llm_run.get('token_count', 0)} tokens)"
            last_event["updated_at"] = now
            await self.broadcast(last_event)

    async def set_llm_active(self, node_name: str | None) -> None:
        self.state["llm_active_node"] = node_name
        await self.broadcast({"type": "llm_active_update", "title": "LLM 状态更新", "details": {"active_node": node_name}})

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
        self.model_config_raw = None
        self.running_task = None
        self.state.update({
            "status": "idle",
            "current_node": "",
            "task_complexity": "unknown",
            "todo_list": [],
            "context_tags": ["general"],
            "agent_role": "general",
            "model_output": "",
            "tool_runs": [],
            "events": [],
            "messages": [],
            "map_cards": [],
            "model_config": get_llm_settings(),
            "llm_active_node": None,
            "active_skills": [],
        })

    async def refresh_approvals(self) -> None:
        pending = list_pending_approvals(self.session_id)
        world_state = dict(self.state.get("world_state") or {})
        if pending:
            world_state["pending_approvals"] = pending
        else:
            world_state.pop("pending_approvals", None)
        self.state["world_state"] = world_state

    def has_pending_approvals(self) -> bool:
        return bool((self.state.get("world_state") or {}).get("pending_approvals"))


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
        active_node = self.session.state.get("llm_active_node") or "agent"
        self.session.state["current_node"] = active_node
        self.session.state["_thinking_field_used"] = False
        if self.session.state["model_output"]:
            self.session.state["model_output"] += "\n\n[[MODEL_OUTPUT_ROUND_BREAK]]\n\n"
        await self.session.start_node_llm_run(active_node, prompts)

    async def on_llm_new_token(self, token: str, **kwargs) -> None:
        thinking, content = extract_thinking_and_content(kwargs.get("chunk"))
        text = content or token

        if thinking:
            self.session.state["_thinking_field_used"] = True
            model_output = self.session.state["model_output"]
            last_think = model_output.rfind("<think>")
            last_think_close = model_output.rfind("</think>")
            is_think_open = (last_think != -1) and (last_think_close == -1 or last_think > last_think_close)
            if not is_think_open:
                self.session.state["model_output"] += f"<think>{thinking}"
            else:
                self.session.state["model_output"] += thinking
            await self.session.update_node_llm_run(thinking, token_type="thinking")

        if text:
            if self.session.state.get("_thinking_field_used"):
                model_output = self.session.state["model_output"]
                last_think = model_output.rfind("<think>")
                last_think_close = model_output.rfind("</think>")
                is_think_open = (last_think != -1) and (last_think_close == -1 or last_think > last_think_close)
                if is_think_open:
                    self.session.state["model_output"] += f"</think>{text}"
                else:
                    self.session.state["model_output"] += text
            else:
                self.session.state["model_output"] += text
            await self.session.update_node_llm_run(text)

    async def on_llm_end(self, response, **kwargs):
        if self.session.state.get("_thinking_field_used"):
            model_output = self.session.state["model_output"]
            last_think = model_output.rfind("<think>")
            last_think_close = model_output.rfind("</think>")
            is_think_open = (last_think != -1) and (last_think_close == -1 or last_think > last_think_close)
            if is_think_open:
                self.session.state["model_output"] += "</think>"
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
        "task_complexity": session.state.get("task_complexity", "unknown"),
        "todo_list": session.state.get("todo_list", []),
        "context_tags": session.state.get("context_tags", ["general"]),
        "world_state": session.state.get("world_state", {}),
        "orchestrator_next": session.state.get("orchestrator_next", "agent"),
        "agent_role": session.state.get("agent_role", "general"),
    }
    config = {
        "configurable": {
            "thread_id": session.thread_id,
            "session_id": session_id,
            "llm_settings": session.model_config_raw or normalize_llm_settings(None),
        },
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
                    if node_name in {"agent", "network_specialist_agent"} and "llm_run" in details:
                        token_count = details["llm_run"].get("token_count", 0)
                        last_event["title"] = f"节点更新: {node_name} (模型调用完成, {token_count} tokens)"
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
                    previous_agent_role = session.state.get("agent_role", "general")
                    next_todo = node_update.get("todo_list", [])
                    next_complexity = node_update.get("task_complexity", "unknown")
                    next_route = node_update.get("orchestrator_next", "")
                    next_agent_role = node_update.get("agent_role", session.state.get("agent_role", "general"))

                    session.state["task_complexity"] = node_update.get("task_complexity", "unknown")
                    session.state["todo_list"] = next_todo
                    session.state["orchestrator_next"] = next_route
                    session.state["agent_role"] = next_agent_role
                    session.state["context_tags"] = node_update.get("context_tags", session.state.get("context_tags", ["general"]))
                    session.state["active_skills"] = node_update.get("active_skills", session.state.get("active_skills", []))

                    todo_changed = normalized_json(previous_todo) != normalized_json(next_todo)
                    complexity_changed = previous_complexity != next_complexity
                    route_changed = previous_next != next_route
                    agent_role_changed = previous_agent_role != next_agent_role

                    if todo_changed:

                        await session.publish({
                            "type": "todo_update",
                            "title": "任务计划已更新",

                            "details": {
                                "task_complexity": session.state["task_complexity"],
                                "previous_task_complexity": previous_complexity,
                                "orchestrator_next": next_route,
                                "previous_orchestrator_next": previous_next,
                                "agent_role": next_agent_role,
                                "previous_agent_role": previous_agent_role,
                                "changed": {
                                    "todo_list": todo_changed,
                                    "task_complexity": complexity_changed,
                                    "orchestrator_next": route_changed,
                                    "agent_role": agent_role_changed,
                                },
                                "previous_todo_list": make_json_safe(previous_todo),
                                "current_todo_list": make_json_safe(session.state["todo_list"]),
                            },
                        })

                if node_name == "memory":
                    session.state["world_state"] = node_update.get("world_state", session.state.get("world_state", {}))
                    if session.has_pending_approvals():
                        session.state["status"] = "awaiting_approval"
                        session.state["current_node"] = ""
                        await session.publish({
                            "type": "approval_required",
                            "title": "等待用户审批",
                            "details": {"pending_approvals": session.state["world_state"].get("pending_approvals", [])},
                        })
                        return

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


@app.get("/api/model-config")
async def get_model_config():
    return get_llm_settings()


def mapbox_browser_token() -> str:
    public_token = os.getenv("MAPBOX_PUBLIC_TOKEN") or ""
    if public_token:
        return public_token
    fallback = os.getenv("MAPBOX_ACCESS_TOKEN") or os.getenv("MAPBOX_API_KEY") or ""
    return fallback if fallback.startswith("pk.") else ""


@app.get("/api/mapbox-config")
async def get_mapbox_config():
    token = mapbox_browser_token()
    return {"configured": bool(token), "token": token}


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

    log_user_question(f"web:{session_id}", message)

    try:
        model_config_raw = normalize_llm_settings(payload.llm_config)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    model_config = redact_llm_settings(model_config_raw)
    session.model_config_raw = model_config_raw

    user_message = HumanMessage(content=message)
    session.memory_messages.append(user_message)
    session.state.update({
        "status": "running",
        "current_node": "orchestrator",
        "task_complexity": "unknown",
        "todo_list": [],
        "context_tags": ["general"],
        "agent_role": "general",
        "world_state": {},
        "model_output": "",
        "tool_runs": [],
        "events": [],
        "messages": [serialize_message(m) for m in session.memory_messages],
        "map_cards": session.state.get("map_cards", []),
        "model_config": model_config,
        "llm_active_node": None,
    })
    await session.publish({
        "type": "run_start",
        "title": "任务开始",
        "details": {"user_message": message, "thread_id": session.thread_id},
    })
    session.running_task = asyncio.create_task(run_agent(user_message, session, session_id))
    return {"status": "started", "session_id": session_id, "state": session.snapshot()}


async def resume_after_approval(session_id: str, session: ConsoleSession, approval: dict[str, Any]) -> None:
    if session.running_task and not session.running_task.done():
        return
    status = approval.get("status", "")
    target = approval.get("target_uri") or approval.get("host_path") or approval.get("target_path", "")
    message = HumanMessage(content=f"用户已处理审批 {approval.get('id')}: {status} {target}。请基于当前 world_state 继续任务。")
    session.memory_messages.append(message)
    if not session.model_config_raw:
        session.model_config_raw = normalize_llm_settings(None)
        session.state["model_config"] = redact_llm_settings(session.model_config_raw)
    session.state.update({
        "status": "running",
        "current_node": "orchestrator",
        "model_output": "",
        "tool_runs": [],
        "messages": [serialize_message(m) for m in session.memory_messages],
        "llm_active_node": None,
    })
    await session.publish({
        "type": "run_start",
        "title": "审批后继续任务",
        "details": {"approval": approval, "thread_id": session.thread_id},
    })
    session.running_task = asyncio.create_task(run_agent(message, session, session_id))


@app.post("/api/stop")
async def stop(request: Request):
    _, session = resolve_session(request)
    if session.running_task and not session.running_task.done():
        session.running_task.cancel()
        return {"status": "stopping"}
    return {"status": "idle"}


@app.get("/api/approvals")
async def get_approvals(request: Request):
    session_id, _ = resolve_session(request)
    return {"session_id": session_id, "approvals": list_approvals(session_id)}


@app.post("/api/approvals/approve")
async def approve_approval(request: Request, payload: ApprovalDecisionRequest):
    session_id, session = resolve_session(request)
    try:
        approval = approve_pending_approval(session_id, payload.approval_id)
    except SandboxError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await session.refresh_approvals()
    await session.publish({
        "type": "approval_applied",
        "title": f"审批已批准: {approval.get('target_uri') or approval.get('host_path') or approval.get('target_path', '')}",
        "details": {"approval": approval},
    })
    await resume_after_approval(session_id, session, approval)
    return {"status": "applied", "approval": approval, "state": session.snapshot()}


@app.post("/api/approvals/reject")
async def reject_approval_endpoint(request: Request, payload: ApprovalDecisionRequest):
    session_id, session = resolve_session(request)
    try:
        approval = reject_approval(session_id, payload.approval_id)
    except SandboxError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await session.refresh_approvals()
    await session.publish({
        "type": "approval_rejected",
        "title": f"审批已拒绝: {approval.get('target_uri') or approval.get('host_path') or approval.get('target_path', '')}",
        "details": {"approval": approval},
    })
    await resume_after_approval(session_id, session, approval)
    return {"status": "rejected", "approval": approval, "state": session.snapshot()}


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

