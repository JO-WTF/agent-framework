from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from app.agents.contracts import AGENT_CONTRACTS
from app.memory.store import make_json_safe_for_storage, normalize_context_tags, summarize_text

MEMORY_SCOPES = {"global", "session", "agent_local", "artifact", "task"}
GLOBAL_DEFER_KINDS = {"preference", "project_fact", "architecture_decision", "skill"}
TEMPORARY_KINDS = {"temporary_state", "progress", "scratchpad"}
MAX_PROPOSALS_PER_TURN = 5
MAX_KEY_CHARS = 80
MAX_VALUE_CHARS = 500
MAX_EVIDENCE_CHARS = 300
MAX_MEMORY_VIEW_ITEMS = 80
MAX_ROUTED_RECORDS = 40
MAX_CONFLICTS = 20

def _now() -> str:
    return datetime.now().isoformat()


def _clean_key(value: Any) -> str:
    key = str(value or "").strip().lower().replace(" ", "_").replace("-", "_")
    return key[:MAX_KEY_CHARS]


def _clean_scope(value: Any) -> str:
    scope = str(value or "session").strip().lower()
    return scope if scope in MEMORY_SCOPES else "session"


def _confidence(value: Any) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        confidence = 0.5
    return max(0.0, min(1.0, confidence))


def normalize_memory_proposal(raw: dict[str, Any], *, default_source: str = "memory_manager") -> dict[str, Any] | None:
    key = _clean_key(raw.get("key"))
    if not key:
        return None

    value = raw.get("value")
    if isinstance(value, (dict, list)):
        compact_value = make_json_safe_for_storage(value)
    else:
        compact_value = summarize_text(str(value or "").strip(), max_chars=MAX_VALUE_CHARS)
    if compact_value in ("", None, [], {}):
        return None

    evidence = summarize_text(str(raw.get("evidence") or ""), max_chars=MAX_EVIDENCE_CHARS)
    source_agent = str(raw.get("source_agent") or raw.get("source") or default_source).strip() or default_source
    scope = _clean_scope(raw.get("scope"))
    kind = str(raw.get("kind") or "fact").strip().lower().replace(" ", "_")[:48]
    owner = str(raw.get("owner") or source_agent).strip()[:48]

    return {
        "id": str(raw.get("id") or f"mem-{abs(hash((key, str(compact_value), source_agent))) % 10_000_000:07d}"),
        "created_at": str(raw.get("created_at") or _now()),
        "scope": scope,
        "kind": kind,
        "key": key,
        "value": compact_value,
        "confidence": _confidence(raw.get("confidence", 0.7)),
        "source_agent": source_agent,
        "owner": owner,
        "evidence": evidence,
        "ttl": str(raw.get("ttl") or ("long_term" if scope == "global" else "session"))[:48],
        "tags": normalize_context_tags(raw.get("tags")),
    }


def _proposal_value_equals(left: Any, right: Any) -> bool:
    return make_json_safe_for_storage(left) == make_json_safe_for_storage(right)


def _route_one(proposal: dict[str, Any], view: dict[str, Any]) -> tuple[str, str]:
    if proposal["confidence"] < 0.35:
        return "rejected", "confidence_below_threshold"
    if len(proposal["key"]) > MAX_KEY_CHARS:
        return "rejected", "key_too_long"
    if proposal["scope"] == "global" and proposal["kind"] in TEMPORARY_KINDS:
        return "rejected", "temporary_state_cannot_be_global"

    existing = view.get(proposal["key"])
    if existing:
        if _proposal_value_equals(existing.get("value"), proposal["value"]):
            return "accepted", "duplicate_same_value"
        if existing.get("owner") and existing.get("owner") != proposal["owner"]:
            return "needs_llm", "owner_conflict"
        if proposal["scope"] != "global":
            return "accepted", "same_owner_version_update"
        return "needs_llm", "same_key_different_value"

    if proposal["scope"] == "global":
        if proposal["kind"] in GLOBAL_DEFER_KINDS or proposal["confidence"] >= 0.85:
            return "deferred", "global_write_deferred_for_batch_arbitration"
        return "rejected", "global_write_requires_high_confidence_or_supported_kind"

    return "accepted", f"{proposal['scope']}_write_fast_path"


def route_memory_proposals(
    raw_proposals: list[dict[str, Any]] | None,
    previous_memory: dict[str, Any] | None,
    *,
    default_source: str = "memory_manager",
) -> dict[str, Any]:
    memory = dict(previous_memory or {})
    view = dict(memory.get("view") or {})
    routed = list(memory.get("routed") or [])
    conflicts = list(memory.get("conflicts") or [])
    stats = dict(memory.get("stats") or {})

    normalized: list[dict[str, Any]] = []
    for raw in list(raw_proposals or [])[:MAX_PROPOSALS_PER_TURN]:
        if isinstance(raw, dict):
            proposal = normalize_memory_proposal(raw, default_source=default_source)
            if proposal:
                normalized.append(proposal)

    for proposal in normalized:
        status, reason = _route_one(proposal, view)
        record = {"status": status, "reason": reason, "proposal": proposal, "routed_at": _now()}
        routed.insert(0, record)
        stats[status] = int(stats.get(status, 0)) + 1

        if status == "accepted":
            view[proposal["key"]] = {
                "value": proposal["value"],
                "scope": proposal["scope"],
                "kind": proposal["kind"],
                "owner": proposal["owner"],
                "source_agent": proposal["source_agent"],
                "confidence": proposal["confidence"],
                "tags": proposal["tags"],
                "updated_at": _now(),
            }
        elif status == "needs_llm":
            conflicts.insert(0, {
                "key": proposal["key"],
                "reason": reason,
                "incoming": proposal,
                "existing": view.get(proposal["key"]),
                "status": "needs_arbitration",
                "created_at": _now(),
            })

    if len(view) > MAX_MEMORY_VIEW_ITEMS:
        view = dict(list(view.items())[-MAX_MEMORY_VIEW_ITEMS:])

    return make_json_safe_for_storage({
        "view": view,
        "routed": routed[:MAX_ROUTED_RECORDS],
        "conflicts": conflicts[:MAX_CONFLICTS],
        "stats": stats,
        "last_routed_at": _now() if normalized else memory.get("last_routed_at"),
        "policy": {
            "hot_path": "rule_based_no_llm",
            "global_writes": "defer_or_needs_arbitration",
            "default_write_scope": "agent_local_or_session",
            "max_proposals_per_turn": MAX_PROPOSALS_PER_TURN,
        },
    })


def build_task_ledger(state: dict[str, Any], previous: dict[str, Any] | None = None) -> dict[str, Any]:
    previous = dict(previous or {})
    todo_list = state.get("todo_list") or previous.get("todo_list", [])
    open_items = []
    completed_count = 0

    def walk(items: list[dict[str, Any]]) -> None:
        nonlocal completed_count
        for item in items:
            status = item.get("status", "pending")
            if status == "completed":
                completed_count += 1
            elif len(open_items) < 8:
                open_items.append({
                    "id": item.get("id", ""),
                    "title": summarize_text(str(item.get("title", "")), max_chars=120),
                    "status": status,
                    "note": summarize_text(str(item.get("note", "")), max_chars=160),
                })
            walk(item.get("children") or [])

    walk(todo_list)
    return make_json_safe_for_storage({
        "task_complexity": state.get("task_complexity", previous.get("task_complexity", "unknown")),
        "active_agent_role": state.get("agent_role", previous.get("active_agent_role", "general")),
        "orchestrator_next": state.get("orchestrator_next", previous.get("orchestrator_next", "agent")),
        "context_tags": normalize_context_tags(state.get("context_tags", previous.get("context_tags"))),
        "open_items": open_items,
        "completed_count": completed_count,
        "todo_count": len(todo_list),
        "updated_at": _now(),
    })


def derive_memory_proposals_from_state(state: dict[str, Any]) -> list[dict[str, Any]]:
    proposals: list[dict[str, Any]] = []
    agent_role = state.get("agent_role") or "general"
    if agent_role:
        proposals.append({
            "scope": "task",
            "kind": "delegation",
            "key": "task.current.active_agent_role",
            "value": agent_role,
            "confidence": 1.0,
            "source_agent": "orchestrator",
            "owner": "orchestrator",
            "evidence": "orchestrator selected active agent role",
            "tags": state.get("context_tags"),
        })

    if state.get("todo_list"):
        proposals.append({
            "scope": "task",
            "kind": "progress",
            "key": "task.current.ledger",
            "value": build_task_ledger(state),
            "confidence": 1.0,
            "source_agent": "orchestrator",
            "owner": "orchestrator",
            "evidence": "todo_list is confirmed graph state",
            "tags": state.get("context_tags"),
        })

    return proposals[:MAX_PROPOSALS_PER_TURN]


def select_relevant_memory_view(
    memory: dict[str, Any] | None,
    *,
    context_tags: list[str] | str | None = None,
    agent_role: str | None = None,
    limit: int = 8,
) -> dict[str, Any]:
    view = (memory or {}).get("view") or {}
    selected_tags = set(normalize_context_tags(context_tags))
    selected: dict[str, Any] = {}

    for key, item in view.items():
        item_tags = set(normalize_context_tags(item.get("tags")))
        owner = str(item.get("owner") or "")
        if (
            selected_tags.intersection(item_tags)
            or key.startswith("task.")
            or key.startswith("project.")
            or (agent_role and owner in {agent_role, "orchestrator", "memory_manager"})
        ):
            selected[key] = item
        if len(selected) >= limit:
            break
    return selected


def format_compact_memory_context(state: dict[str, Any], max_chars: int = 1600) -> str:
    world_state = state.get("world_state") or {}
    task_ledger = world_state.get("task_ledger") or build_task_ledger(state)
    memory = world_state.get("memory") or {}
    relevant_memory = select_relevant_memory_view(
        memory,
        context_tags=state.get("context_tags"),
        agent_role=state.get("agent_role", "general"),
    )
    runtime = world_state.get("runtime_environment") or {}
    sandbox = world_state.get("sandbox")
    pending_approvals = world_state.get("pending_approvals") or []
    tool_results = (world_state.get("tool_results") or [])[-5:]

    compact = {
        "task_ledger": task_ledger,
        "agent_contract": AGENT_CONTRACTS.get(state.get("agent_role", "general"), AGENT_CONTRACTS["general"]),
        "memory_policy": (memory.get("policy") or {
            "hot_path": "rule_based_no_llm",
            "global_writes": "defer_or_needs_arbitration",
        }),
        "relevant_memory": relevant_memory,
        "memory_conflicts": (memory.get("conflicts") or [])[:3],
        "recent_tool_results": tool_results,
        "sandbox": sandbox,
        "pending_approvals": pending_approvals[:5],
        "runtime_write_policy": runtime.get("write_policy"),
        "runtime_paths": runtime.get("sandbox_container_paths"),
    }
    text = "Compact Memory Context:\n" + json.dumps(make_json_safe_for_storage(compact), ensure_ascii=False, default=str)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n...（Compact Memory Context 已按 token 预算截断）"
    return text
