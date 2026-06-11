# 入口、配置与运行期模块说明

## 1. CLI 入口

文件：`app/cli.py`

职责：

- 构造 LangGraph 主图。
- 创建 `MemorySaver()` checkpointer。
- 维护 CLI 级 `memory_messages`。
- 支持 `/clear`、`/quit`、`/exit`、`/q`。
- 将最终 AI 回复追加回会话记忆。

CLI 每轮请求初始状态：

```python
initial_input = {
    "messages": memory_messages,
    "revision_count": 0,
    "eval_status": "",
    "session_id": "cli",
    "task_complexity": "unknown",
    "todo_list": [],
    "context_tags": ["general"],
    "world_state": {},
    "orchestrator_next": "agent",
}
```

设计意图：CLI 保持薄入口，真正的任务流由状态图处理。

## 2. Web 入口

文件：

- `app/web.py`
- `app/web_static/index.html`
- `app/web_static/app.js`
- `app/web_static/styles.css`

Web 入口复用 `build_agent_graph()`，但使用 streaming updates 展示节点事件：

- `GET /`：返回前端页面。
- `GET /api/state`：返回当前会话快照。
- `POST /api/chat`：提交用户消息并启动后台任务。
- `POST /api/stop`：取消运行中的任务。
- `POST /api/clear`：重置当前 Web 会话的数据（如消息历史和运行记录），但保留当前 Session ID。
- “新建会话”：前端点击后会清理 LocalStorage 中的 `agent_session_id` 并自动重载，在前后端发起并建立全新的 Session ID 和独立会话。
- `WS /ws`：推送状态快照和节点事件。

`ConsoleSession` 保存每个 Web 会话的运行态：

- `session_id`
- `thread_id`
- `memory_messages`
- `running_task`
- `subscribers`
- `state`

Web 层设计目标是可观察性。它不改变 Agent 决策，只把节点更新、tool runs、todo 更新和 `world_state` 推给前端。

## 3. 配置层

文件：`app/config.py`

职责：

- 加载 `.env`。
- 加载 `config/prompts.yaml`。
- 定义 `AgentState`。
- 初始化 `llm_client`。
- 初始化 `TavilyClient`。
- 提供 CLI 流式回调 `StreamingConsoleCallback`。

支持的 LLM Provider：

| Provider | 行为 |
| --- | --- |
| `openai` | 使用 `OPENAI_API_KEY` 或 `LLM_API_KEY`，可选 `LLM_BASE_URL`。 |
| `deepseek` | 默认 `https://api.deepseek.com/v1`，默认模型 `deepseek-v4-flash`。 |
| `ollama` | 默认 `http://localhost:11434/v1`。 |
| `llamacpp` | 默认 `http://isc.ai.huawei.com:11434/v1`，默认模型 `qwen3.6:latest`。 |
| 其他 | 作为 OpenAI-compatible 服务处理。 |

关键环境变量：

| 变量 | 说明 |
| --- | --- |
| `LLM_PROVIDER` | 模型供应商。 |
| `LLM_MODEL_NAME` | 模型名称。 |
| `LLM_API_KEY` | 通用 API key。 |
| `LLM_BASE_URL` | OpenAI-compatible base URL。 |
| `LLM_TEMPERATURE` | 温度，默认 `0.1`。 |
| `TAVILY_API_KEY` | Tavily 搜索 key。 |
| `MAPBOX_PUBLIC_TOKEN` | 可选，Web 对话框 Mapbox 地图卡片使用；该 token 会发送到浏览器，应使用 Mapbox public token。 |
| `MAPBOX_ACCESS_TOKEN` / `MAPBOX_API_KEY` | 可选，Network Specialist Agent 的 Mapbox 地址编码与反编码 key。只有以 `pk.` 开头时才会作为地图卡片浏览器 token 的 fallback。 |
| `HERE_API_KEY` / `HERE_APIKEY` | 可选，Network Specialist Agent 的 HERE 地址编码与反编码 key。 |
| `MAX_CONTEXT_SIZE_KB` | 最大上下文序列化大小，默认 512。 |

## 4. Prompt 层

文件：`config/prompts.yaml`

主要分区：

- `global_context`：全局系统信息，例如当前时间。
- `orchestrator`：复杂度判断、todo 规则、路由规则、context tags 输出。
- `agent_brain`：Brain 行动准则。
- `evaluator`：最终 QA 标准。
- `tool_execution.fix_args`：工具参数修复器提示词。
- `tools`：工具自然语言描述。

设计细节：工具描述直接影响模型是否调用工具。新增工具时必须把描述写得具体，说明“何时调用”和“参数要求”。

## 5. 公共节点工具

文件：`app/nodes/common.py`

职责：

- `get_system_prompt()`：合并动态标签、静态规则、Agent Notes、全局 prompt 和节点 prompt。
- `parse_json_object()`：容忍 fenced code block 或前后解释文本，提取 JSON 对象。
- `format_todo_context()`：把 todo 和 `world_state` 格式化给 Brain/Evaluator。
- `summarize_recent_messages()`：把最近消息压缩成调试/判断用文本。
- `infer_context_tags_from_state()`：从消息、tool calls、todo 推断上下文标签。
- `default_orchestrator_next()`：代码层路由兜底。

## 6. 运行期数据

文件：`app/runtime_paths.py`

路径约定：

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

这些文件被 `.gitignore` 忽略，属于本地运行数据，不应提交。

## 7. 日志

文件：

- `app/logging_config.py`
- `config/logging.yaml`

日志用于观察节点进入、工具调用、todo 更新、质检结果和错误。Web 端另有 `events.jsonl`，用于保留前端时间线事件。

## 8. 测试模块

文件：

- `tests/test_memory_manager.py`
- `tests/test_tool_execution_subgraph.py`
- `tests/test_dynamic_context.py`

测试重点不是覆盖所有 prompt 行为，而是覆盖代码层不应被 LLM 随意突破的约束：

- Memory Manager 什么时候归档。
- 路由是否受 `last_node` 控制。
- 工具子图是否隔离内部历史。
- 缺依赖是否变成外部动作，而不是自动安装。
- 危险命令修复是否被拒绝。
- 动态上下文是否按标签懒加载。

## 11. Network Specialist Agent 入口状态

CLI 和 Web 每轮初始化状态时会设置 `agent_role="general"`。当 Orchestrator 识别到地图、物流网络、仓库、站点、路径、配送、覆盖、服务半径、选址或仓网规划任务时，会把 `agent_role` 更新为 `network`，随后 Memory Manager 将下一次 agent 类执行路由到 `network_specialist_agent`。
