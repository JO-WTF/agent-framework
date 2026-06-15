# Memory Manager 设计说明

## 1. 模块位置

主要文件：

- `app/nodes/memory_manager.py`
- `app/memory/proposals.py`
- `app/memory/store.py`
- `app/runtime_paths.py`

Memory Manager 是主图里的“状态固化 + 结构化 memory 路由 + 历史治理 + 路由枢纽”。

## 2. 为什么需要 Memory Manager

Agent 任务会产生大量中间消息：用户输入、LLM 推理、工具调用、工具输出、质检打回。把所有消息无限塞回模型会带来三个问题：

- 上下文窗口膨胀，成本和延迟上升。
- 早期关键信息被大量流水账稀释。
- 工具结果可能很长，反复进入 prompt 会污染推理。

Memory Manager 的设计是先把已确认事实固化成紧凑 `world_state`，再对早期消息做归档和裁剪。Brain 和 Evaluator 每轮拿到的是“近期上下文 + Compact Memory Context”，而不是完整 `world_state`。

性能原则：

- 热路径不调用 LLM。
- 普通 agent 只提交 `memory_proposals`，不能直接覆盖 global memory。
- `session`、`task`、`agent_local` 和 `artifact` 写入优先走规则快路径。
- `global` 写入默认延迟批处理；同 key 不同 owner 或 global 冲突标记为 `needs_arbitration`。
- prompt 注入只选择 task ledger、相关 memory、最近工具摘要和必要运行策略。

## 3. `world_state` 结构

`build_world_state()` 会合并旧状态和当前状态：

```python
world_state = {
    "task_complexity": ...,
    "context_tags": ...,
    "todo_list": ...,
    "task_ledger": ...,
    "agent_contracts": ...,
    "memory": ...,
    "runtime_environment": ...,
    "updated_at": ...,
    "tool_results": ...,
    "sandbox": ...,
    "pending_approvals": ...,
    "last_final_reply": ...,
}
```

字段说明：

- `task_complexity`：当前任务复杂度。
- `context_tags`：当前动态上下文标签。
- `todo_list`：Orchestrator 维护的分级 todo。
- `task_ledger`：当前任务账本，包含活跃 agent、开放事项、已完成数量和上下文标签。当前任务状态不写入长期 global memory。
- `agent_contracts`：General、Network Specialist 和 Memory Manager 的职责边界，用于约束多 agent 协作。
- `memory`：结构化 memory view、proposal 路由记录、冲突队列和写入策略。
- `runtime_environment`：当前宿主系统、项目根目录、沙箱模式、容器路径、路径协议和写入策略。
- `tool_results`：最近工具结果摘要，按 `tool_call_id` 合并去重，最多保留 30 条。
- `sandbox`：当前会话 Docker 沙箱运行态。未启动时为 `{"mode": "docker", "status": "not_started"}`；启动后包含容器名、镜像、只读源码目录和共享工作目录，并通过 `docker inspect` 做轻量健康检查。
- `pending_approvals`：当前会话等待用户处理的审批申请，例如沙箱文件写回。
- `last_final_reply`：最近自然语言最终答复摘要。
- `updated_at`：固化时间。

例子：一次 `run_command` 返回 `标准输出:\nhello` 后，`world_state["tool_results"]` 会保存：

```json
{
  "tool_call_id": "call-1",
  "summary": "标准输出:\nhello",
  "updated_at": "..."
}
```

后续 Brain 不需要看到完整历史，也能知道某个工具调用已经完成并返回了什么。

## 4. Memory Proposal 路由

`app/memory/proposals.py` 提供确定性 memory 路由：

```json
{
  "scope": "session",
  "kind": "decision",
  "key": "project.architecture.memory.write_policy",
  "value": "普通 agent 只能提交 proposal",
  "confidence": 0.95,
  "source_agent": "general",
  "owner": "general",
  "evidence": "任务中确认的架构约束",
  "tags": ["memory"]
}
```

路由结果：

- `accepted`：写入 `memory.view`。适用于 session/task/agent_local/artifact 快路径、重复同值、同 owner 版本更新。
- `rejected`：低置信度、缺关键字段、临时状态写 global 等。
- `deferred`：global 写入延迟到批处理或用户确认，不阻塞主流程。
- `needs_llm`：同 key 不同 owner、global 冲突等需要语义仲裁的情况，记录到 `memory.conflicts`。

每轮最多处理 5 条 proposal，单条 key/value/evidence 都有长度上限，避免 memory 阶段反过来制造 token 膨胀。

## 5. Compact Memory Context

`format_todo_context()` 默认不再把完整 `world_state` 塞给模型，而是调用 `format_compact_memory_context()` 输出：

- `task_ledger`
- 当前 agent contract
- memory policy 和最多 3 条冲突
- 按 `context_tags` 和 owner 筛选后的相关 memory
- 最近 5 条工具结果摘要
- sandbox、pending approvals 和写入路径策略

这让 Memory Manager 可以继续保留完整可观察状态，同时降低 Agent/Evaluator 每轮 prompt 成本。

## 6. 归档策略

Memory Manager 有两级上下文治理。

第一级在 `memory_manager_node()`：

- 只有 `world_state` 已经包含 todo、工具结果或最终答复时，才认为有“已固化状态”。
- 消息数超过 `MEMORY_MANAGER_MIN_MESSAGES = 12` 或上下文超过 `128KB` 时，选择早期消息归档。
- 保留最近 `MEMORY_MANAGER_KEEP_RECENT = 8` 条。
- 用 `RemoveMessage` 从 LangGraph 消息流中删除已归档消息。

第二级在 `app/memory/store.py` 的 `trim_messages()`：

- 默认保留最近 `DEFAULT_MESSAGE_WINDOW = 8` 条。
- 早期消息中保留工具调用、工具结果、含关键字的消息。
- 其余消息写入 `conversation_archive.json`，并用一条“自动压缩早期对话”摘要替代。
- 通过 `MAX_CONTEXT_SIZE_KB` 环境变量控制最大序列化上下文尺寸，默认 512KB。

设计重点：只有当结构化状态足够承接历史时，才积极删除早期消息。否则宁可保留，以免丢失任务背景。

## 7. 会话隔离

运行期路径由 `app/runtime_paths.py` 定义：

```text
.data/
├── global/
│   └── agent_memory.json
└── sessions/
    └── {session_id}/
        ├── conversation_archive.json
        ├── tool_results.json
        └── events.jsonl
```

- CLI 默认 `session_id="cli"`。
- Web 为每个浏览器会话创建独立 `session_id`。
- 工具结果、对话归档和事件日志都按 session 分开。

## 8. 动态上下文标签

`app/memory/store.py` 支持：

- `normalize_context_tags()`：清洗标签格式。
- `infer_context_tags()`：根据文本启发式识别标签。
- `load_static_guidelines()`：按标签加载 `STATIC_GUIDELINES.md` 中的规则片段。
- `load_agent_notes()`：按标签加载 `.data/global/agent_memory.json` 中的经验笔记。

已知标签包括：

```text
general, database, file_system, api_call, search, python, command,
tool_error, memory, security, web
```

设计初衷：不要每轮把所有规则都塞进系统提示词。比如文件任务只加载 `[file_system]` 规则，命令错误才加载 `tool_error` 笔记。

## 9. Agent Notes

工具层会在失败时调用 `save_agent_note()` 写全局经验：

- `run_python` 报错会记录 Python traceback 摘要。
- `run_command` 失败或超时会记录命令失败经验。

这些笔记不是完整长期记忆，而是“失败经验缓存”。它们按 `tags` 懒加载，帮助后续相似任务少犯同类错误。

## 10. 路由职责

`route_after_memory()` 是主图路由核心。它结合 `last_node` 和最后消息类型判断下一跳：

- Agent 产生 tool calls：去 `tools`。
- Agent 产生自然语言：回 `orchestrator`。
- Tools 完成：回 `orchestrator`。
- Orchestrator 决定继续：去 `agent`。
- Orchestrator 决定质检：由 Orchestrator 条件边直接去 `evaluate`，不再经由 Memory Manager。

把路由放在 Memory Manager 后面，是为了保证每次跳转前都先有机会固化状态。

## 11. 设计细节与注意点

- `_select_messages_to_archive()` 会避免保留历史以 `ToolMessage` 开头，防止工具协议断裂。
- 同 owner 的非 global memory 更新走版本更新快路径，避免 task ledger 每轮变动触发仲裁。
- 不同 owner 写同 key 不会覆盖旧值，而是进入 `memory.conflicts`。
- global memory 写入不阻塞主流程，默认 `deferred`。
- `tool_results` 按 `tool_call_id` 合并，避免同一工具调用反复写入。
- `make_json_safe_for_storage()` 统一把 LangChain 消息转成可存储 JSON。
- 归档后台执行：有 event loop 时用 `asyncio.create_task()`，避免阻塞主流程。
- `trim_messages()` 会跳过旧的“自动压缩早期对话”摘要，避免摘要嵌套。
