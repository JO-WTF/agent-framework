from __future__ import annotations

import json
from typing import Any

AGENT_CONTRACTS: dict[str, dict[str, Any]] = {
    "general": {
        "role": "coordinator",
        "summary": "通用协调与执行 agent，处理非专业领域任务，并在需要时等待专业 agent 接管。",
        "tool_categories": ["search", "sandbox", "results", "execution", "skills"],
        "responsibilities": [
            "理解用户意图并执行通用检索、分析、代码和命令类任务",
            "在专业任务需要时依赖 Orchestrator 指派对应 specialist",
            "汇总专业 agent 结果并形成最终回复",
            "只提交 memory proposal，不直接覆盖 global memory",
        ],
        "planning_boundaries": [
            "可以接收目标、数据需求、约束和验收标准",
            "不应接收地图渲染、地理编码等 network specialist 专属执行计划",
            "不应接收要求直接覆盖 global memory 的计划",
        ],
        "cannot": [
            "直接覆盖 global memory",
            "执行地图渲染等 network specialist 专家工具",
            "覆盖专业 agent 的 agent_local memory",
        ],
    },
    "network": {
        "role": "geospatial_specialist",
        "summary": "地理空间、地理编码、路线、距离和地图可视化 specialist。",
        "tool_categories": ["search", "sandbox", "results", "execution", "skills", "geo", "visualization"],
        "responsibilities": [
            "处理地点、地址、经纬度、路线、距离和地图展示",
            "使用地理编码和可视化工具产出结构化地图结果",
            "返回地图 widget、工具结果引用或必要 artifact 引用",
            "只提交 memory proposal，不直接覆盖 global memory",
        ],
        "planning_boundaries": [
            "可以接收地点清单、坐标数据需求、地图展示目标和验收标准",
            "除非用户明确指定，不应由 Orchestrator 预先规定具体地图库、文件格式或导出方式",
            "具体工具和实现路线由 network specialist 根据可用工具选择",
        ],
        "cannot": [
            "直接覆盖 global memory",
            "改写 General Agent 的任务拆解职责",
            "在用户未要求时把交互式展示任务改成文件导出任务",
        ],
    },
    "memory_manager": {
        "role": "memory_arbiter",
        "summary": "结构化 memory 路由、task ledger 和 compact memory view 管理者。",
        "tool_categories": [],
        "responsibilities": [
            "按规则路由 proposal",
            "维护 task ledger 和 compact memory view",
            "发现冲突并推迟需要语义仲裁的 global 写入",
        ],
        "planning_boundaries": [
            "只接收结构化 memory proposal 或图状态",
            "不执行用户业务任务",
        ],
        "cannot": [
            "在热路径调用 LLM",
            "无证据写入用户长期偏好",
        ],
    },
}


def format_agent_contracts_for_orchestrator(max_chars: int = 4000) -> str:
    """Return compact JSON contracts so Orchestrator can delegate within agent boundaries."""
    payload = {
        name: {
            "role": contract.get("role"),
            "summary": contract.get("summary"),
            "tool_categories": contract.get("tool_categories", []),
            "responsibilities": contract.get("responsibilities", []),
            "planning_boundaries": contract.get("planning_boundaries", []),
            "cannot": contract.get("cannot", []),
        }
        for name, contract in AGENT_CONTRACTS.items()
        if name != "memory_manager"
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n...（Agent contracts 已截断）"
    return text
