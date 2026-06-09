# 状态字段与消息协议

## 1. 为什么需要协议文档

这个项目的稳定性依赖两套协议：

- `AgentState` 字段协议：每个节点读写哪些字段。
- LangChain 消息协议：`AIMessage.tool_calls` 与 `ToolMessage.tool_call_id` 必须正确对应。

如果节点随意改字段或打破消息邻接关系，LangGraph 路由、工具调用和上下文裁剪都会出问题。

## 2. AgentState 字段

定义位置：`app/config.py`

```python
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    revision_count: int
    eval_status: str
    session_id: NotRequired[str]
    task_complexity: NotRequired[str]
    todo_list: NotRequired[list[dict[str, Any]]]
    context_tags: NotRequired[list[str]]
    world_state: NotRequired[dict[str, Any]]
    last_node: NotRequired[str]
    orchestrator_next: NotRequired[str]
    orchestrator_think: NotRequired[str]
    orchestrator_message: NotRequired[str]
    orchestrator_prompt: NotRequired[list[dict[str, str]]]
```

## 3. 字段读写约定

| 字段 | 主要写入者 | 主要读取者 | 约定 |
| --- | --- | --- | --- |
| `messages` | Entry、Agent、Tools、Evaluator、Memory | 所有节点 | 只追加协议消息；Memory 可用 `RemoveMessage` 删除已归档消息。 |
| `revision_count` | Entry 初始化、Evaluator 更新 | Evaluator | 每次 REJECT 加 1，达到 3 后熔断。 |
| `eval_status` | Entry 初始化、Evaluator 更新 | `route_after_evaluation()` | 只用 `PASS` / `REJECT` 语义。 |
| `session_id` | Entry | Memory、Tools、Web | 用于 `.data/sessions/{session_id}/` 隔离。 |
| `task_complexity` | Orchestrator | Brain、Evaluator、Memory | `simple` / `complex` / `unknown`。 |
| `todo_list` | Orchestrator | Brain、Evaluator、Memory、Web | 分级 todo，不要无故删除已有项。 |
| `context_tags` | Orchestrator | Common prompt、Memory、Web | 最多 4 个，来自已知标签集合。 |
| `world_state` | Memory Manager | Brain、Evaluator、Web | 已固化事实板，不放完整大输出。 |
| `last_node` | Orchestrator、Agent、Tools、Evaluator | Memory Manager | 路由关键字段，每个主节点必须设置。 |
| `orchestrator_next` | Orchestrator | Memory Manager、Web | `agent` 或 `evaluate`，代码层仍会校正。 |
| `orchestrator_think` | Orchestrator | Web/debug | 仅观察，不参与路由。 |
| `orchestrator_message` | Orchestrator | Web/debug | 原始 JSON 输出文本。 |
| `orchestrator_prompt` | Orchestrator | Web/debug | 编排器调用时的 prompt。 |

## 4. 消息类型协议

主图中常见消息：

- `HumanMessage`：用户输入，或 Evaluator 追加的 `[质检打回]`。
- `AIMessage`：Brain 的模型输出，可能含 `tool_calls`。
- `ToolMessage`：工具执行结果，必须带 `tool_call_id`。
- `RemoveMessage`：Memory Manager 请求 LangGraph 移除历史消息。

## 5. Tool Calling 邻接关系

工具调用协议要求：

1. Brain 生成 `AIMessage(tool_calls=[...])`。
2. Tools Node 为每个 tool call 返回一个 `ToolMessage`。
3. 每个 `ToolMessage.tool_call_id` 必须等于原始 tool call 的 `id`。
4. 保留窗口不能以孤立 `ToolMessage` 开头。

正确形态：

```text
AIMessage(tool_calls=[{"id": "call-1", "name": "run_command", ...}])
ToolMessage(tool_call_id="call-1", content="标准输出: ...")
```

错误形态：

```text
ToolMessage(tool_call_id="call-1", content="...")
```

如果上下文裁剪后只留下孤立 `ToolMessage`，后续模型调用可能报协议错误或误解工具结果来源。

## 6. `last_node` 路由协议

每个主节点返回时必须设置：

| 节点 | 返回值 |
| --- | --- |
| Orchestrator | `"last_node": "orchestrator"` |
| Agent Brain | `"last_node": "agent"` |
| Tools Node | `"last_node": "tools"` |
| Evaluator | `"last_node": "evaluate"` |

Memory Manager 根据 `last_node` 判断：

- `agent` + tool calls => `tools`
- `agent` + final AI reply => `orchestrator`
- `tools` => `orchestrator`
- `orchestrator` + `orchestrator_next=evaluate` + final AI reply => `evaluate`
- 其他 orchestrator 输出 => `agent`

新增节点时必须明确它会不会进入 Memory Manager，以及是否需要扩展 `route_after_memory()`。

## 7. todo item 协议

todo item 必须包含：

```json
{
  "id": "1",
  "title": "任务标题",
  "status": "pending",
  "note": "当前进展或阻塞原因",
  "children": []
}
```

`status` 只能是：

- `pending`
- `in_progress`
- `completed`
- `blocked`

Brain 和 Evaluator 都依赖这个结构。不要把 todo 变成自由文本。

## 8. world_state 协议

`world_state` 由 Memory Manager 写入，推荐保持紧凑：

```json
{
  "task_complexity": "complex",
  "context_tags": ["command"],
  "todo_list": [],
  "runtime_environment": {
    "host_os": "darwin",
    "cwd": "/path/to/repo",
    "sandbox_mode": "docker",
    "sandbox_container_paths": {
      "work": "/workspace/work",
      "shared_prefix": "/workspace/shared/<name>"
    },
    "path_protocols": ["repo://", "shared://"],
    "write_policy": "Write generated files to /workspace/work, then request approval with apply_sandbox_file before changing repo:// or shared:// targets."
  },
  "updated_at": "...",
  "tool_results": [
    {
      "tool_call_id": "call-1",
      "summary": "标准输出: hello",
      "updated_at": "..."
    }
  ],
  "sandbox": {
    "mode": "docker",
    "status": "running",
    "container": "agent-sandbox-...",
    "image": "jupyter/scipy-notebook:latest",
    "work_dir": "/path/to/.data/sessions/.../sandbox_work/shared"
  },
  "pending_approvals": [
    {
      "id": "approval-...",
      "type": "sandbox_file_writeback",
      "status": "pending",
      "source_path": "result.txt",
      "target_path": "app/foo.py",
      "target_uri": "repo://app/foo.py",
      "overwrite": false,
      "preview": "..."
    }
  ],
  "last_final_reply": "..."
}
```

约定：

- 不存完整长输出，完整内容去 `tool_results.json`。
- `runtime_environment` 只包含对工具和沙箱决策有用的紧凑运行态，不包含环境变量、密钥或本地目录枚举。命令/Python 默认进入 Docker 会话沙箱；读取 repo 外系统目录必须先创建前端审批申请。
- `tool_results` 按 `tool_call_id` 合并。
- `sandbox` 只存会话运行态，不写入长期 memory；当已有容器 metadata 时会通过 `docker inspect` 更新 `running`、`stopped` 或 `missing` 状态。
- `pending_approvals` 只保存等待用户处理的会话审批，不写入长期 memory。
- `last_final_reply` 只保存摘要。

## 9. Entry 初始状态协议

CLI 和 Web 每轮都初始化：

```python
{
    "messages": memory_messages,
    "revision_count": 0,
    "eval_status": "",
    "session_id": "...",
    "task_complexity": "unknown",
    "todo_list": [],
    "context_tags": ["general"],
    "world_state": {},
    "orchestrator_next": "agent",
}
```

如果新增必填状态字段，需要同时更新 CLI、Web、测试和文档。

## 10. 修改协议时的检查清单

- [ ] 是否更新 `AgentState`。
- [ ] CLI 初始状态是否补字段。
- [ ] Web 初始状态和 snapshot 是否补字段。
- [ ] Memory Manager 是否需要固化字段。
- [ ] `format_todo_context()` 或 prompt 是否需要展示字段。
- [ ] 测试是否覆盖默认值和路由。
- [ ] 文档是否同步更新。
