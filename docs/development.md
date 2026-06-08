# 开发者上手指南

## 1. 环境要求

项目是 Python Agent 框架，核心依赖包括 LangGraph、LangChain、OpenAI-compatible Chat API、FastAPI 和 Tavily。

推荐使用仓库内虚拟环境：

```bash
.venv/bin/python --version
```

如果本地没有可用虚拟环境，创建并安装依赖：

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
```

注意：系统 Python 可能没有安装项目依赖。当前仓库里用系统 `python -m pytest tests` 会因为找不到 `langchain_core` 失败；优先使用 `.venv/bin/python`。

## 2. 配置 `.env`

至少需要：

```bash
LLM_PROVIDER=openai
LLM_MODEL_NAME=gpt-4o-mini
LLM_API_KEY=...
TAVILY_API_KEY=...
```

常用变量：

| 变量 | 说明 |
| --- | --- |
| `LLM_PROVIDER` | `openai`、`deepseek`、`ollama`、`llamacpp` 或其他 OpenAI-compatible 服务。 |
| `LLM_MODEL_NAME` | 模型名称。 |
| `LLM_API_KEY` | 通用模型 API key。 |
| `LLM_BASE_URL` | 自定义 base URL。 |
| `LLM_TEMPERATURE` | 温度，默认 `0.1`。 |
| `TAVILY_API_KEY` | Tavily 搜索 API key。 |
| `MAX_CONTEXT_SIZE_KB` | 最大上下文序列化大小，默认 512。 |

不要提交真实 `.env`。`.gitignore` 已忽略 `.env` 和 `.data/`。

## 3. 启动 CLI

```bash
./run_cli.sh
```

CLI 入口是 `app/cli.py`。它会：

- 构建 LangGraph 主图。
- 创建 `MemorySaver()` checkpointer。
- 维护 `memory_messages`。
- 支持 `/clear` 清空会话，`/quit` 退出。

## 4. 启动 Web 控制台

```bash
./run_web.sh
```

Web 入口是 `app/web.py`，前端静态文件在 `app/web_static/`。

主要接口：

- `GET /`
- `GET /api/state`
- `POST /api/chat`
- `POST /api/stop`
- `POST /api/clear`
- `WS /ws`

Web 与 CLI 复用同一张 LangGraph，只是 Web 会把节点更新、todo 变化、工具运行和 `world_state` 通过 WebSocket 推给前端。

## 5. 运行测试

推荐：

```bash
.venv/bin/python -m unittest discover -s tests
```

如果虚拟环境安装了 pytest，也可以：

```bash
.venv/bin/python -m pytest tests
```

当前测试不依赖真实 LLM/Tavily 调用；测试文件会设置 dummy 环境变量，并用 mock 覆盖需要的模型行为。

## 6. 代码组织

```text
app/
├── cli.py                         # CLI 与主图组装
├── web.py                         # Web 控制台
├── config.py                      # AgentState、LLM、Tavily、prompt 加载
├── nodes/                         # Orchestrator/Brain/Memory/Tools/Evaluator
├── memory/store.py                # 历史裁剪、归档、动态上下文
├── tools/                         # 工具实现与注册
└── runtime_paths.py               # .data 路径约定
```

优先阅读：

1. `app/cli.py`：看主图怎么连。
2. `app/config.py`：看状态字段。
3. `app/nodes/memory_manager.py`：看路由和 `world_state`。
4. `app/nodes/tool_execution_subgraph.py`：看工具失败处理。

## 7. 常见开发流程

### 修改节点逻辑

1. 读对应节点文件和 `docs/modules/` 下的模块文档。
2. 确认节点返回是否设置了正确的 `last_node`。
3. 如影响路由，补 `tests/test_memory_manager.py`。
4. 如影响 prompt 输出格式，补解析失败或保守回退测试。

### 修改工具逻辑

1. 修改 `app/tools/` 中具体工具。
2. 必要时修改 `app/nodes/tool_execution_subgraph.py` 的失败分类。
3. 更新 `config/prompts.yaml` 的工具描述。
4. 补 `tests/test_tool_execution_subgraph.py`。

### 修改上下文/记忆逻辑

1. 修改 `app/memory/store.py` 或 `app/nodes/memory_manager.py`。
2. 确认不会破坏 tool call 与 ToolMessage 邻接关系。
3. 补动态上下文或归档测试。

## 8. 运行期数据

运行数据写入：

```text
.data/
├── global/agent_memory.json
└── sessions/{session_id}/
    ├── conversation_archive.json
    ├── tool_results.json
    └── events.jsonl
```

这些文件用于本地调试和会话恢复，不属于源码。
