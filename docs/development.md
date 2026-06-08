# 开发者上手指南

## 1. 环境要求

项目是 Python Agent 框架，核心依赖包括 LangGraph、LangChain、OpenAI-compatible Chat API、FastAPI 和 Tavily。

推荐直接用启动脚本。启动脚本会创建/复用仓库内虚拟环境、安装 Python 依赖、检查 Docker 沙箱依赖，并在缺少 Docker 时询问是否安装：

```bash
./run_web.sh
```

Windows 原生 PowerShell：

```powershell
.\run_web.ps1
```

自动安装 Docker 的规则：

- macOS：通过 Homebrew 安装 Docker Desktop，并尝试启动 Docker Desktop。
- Linux：通过 Docker 官方 convenience script 安装 Docker Engine，并尝试启动 daemon。
- WSL：不在 WSL 内安装 Docker Engine；提示安装 Docker Desktop 并启用 WSL integration。
- Windows 原生 PowerShell：通过 `winget install -e --id Docker.DockerDesktop` 安装 Docker Desktop，并尝试启动 Docker Desktop。
- 所有自动安装都会先询问用户。非交互终端默认拒绝继续，除非显式设置 `AGENT_SETUP_ASSUME_YES=true`。
- 安装 Docker Desktop 后，setup 会等待 Docker daemon 启动，默认最多 180 秒；可用 `AGENT_DOCKER_START_TIMEOUT` 调整。
- 原始日志写入 `logs/setup.log` 和 `logs/setup-steps/`。

如果只想手动准备虚拟环境：

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
| `AGENT_DISABLE_DOCKER_SANDBOX` | 默认不设置。设为 `true` 会禁用 Docker 沙箱，并拒绝 Agent 的命令/Python 执行。 |
| `AGENT_SANDBOX_IMAGE` | Docker 沙箱镜像，默认 `python:3.12-slim`。 |
| `AGENT_SANDBOX_CPUS` | Docker 沙箱 CPU 限制，默认 `2`。 |
| `AGENT_SANDBOX_MEMORY` | Docker 沙箱内存限制，默认 `2g`。 |
| `AGENT_SANDBOX_TIMEOUT` | Docker 沙箱超时秒数，默认 `30`。 |

不要提交真实 `.env`。`.gitignore` 已忽略 `.env` 和 `.data/`。

### Docker 会话沙箱

第一阶段沙箱通过 Docker 提供轻量隔离。它是会话级、懒启动的：

- 每个会话创建一个共享可写目录，挂载到 `/workspace/work`。
- 第一次 `run_command` 或 `run_python` 需要执行时才启动容器。
- 同一会话后续工具调用通过 `docker exec` 进入同一个容器。
- 容器默认开启网络，便于访问公网资源。
- 容器使用非 root 用户、只读根文件系统、`/tmp` tmpfs、CPU/内存/pids/超时限制。
- 可写目录保存在 `.data/sessions/{session_id}/sandbox_work/shared/`，便于宿主侧和其他节点查看产物。
- 容器信息写入 `.data/sessions/{session_id}/sandbox.json`。
- `world_state["sandbox"]` 会读取 `sandbox.json` 并通过 `docker inspect` 做轻量健康检查。
- 沙箱内不能直接修改项目源码或共享目录。需要写回时，先在 `/workspace/work` 生成文件，再用 `apply_sandbox_file` 创建前端审批申请。用户批准后，Web API 才会真正写回 `repo://...` 或已授权的 `shared://<name>/...`。
- 在 Windows 原生环境中，共享目录可以使用 Windows 路径，例如 `C:\Users\alice\Documents\docs`。Docker 容器内仍统一访问 `/workspace/shared/<name>`。

Agent 可用的沙箱控制工具：

| 工具 | 说明 |
| --- | --- |
| `start_sandbox()` | 显式启动当前会话共享容器。 |
| `sandbox_status()` | 查看当前会话沙箱状态，不启动容器。 |
| `stop_sandbox()` | 停止当前会话共享容器。 |
| `add_shared_mount(name, host_path, access="read")` | 为访问本地系统目录创建前端审批申请；批准后记录共享目录（支持 read 只读和 write 读写模式），容器重启后挂载到 `/workspace/shared/<name>`。 |
| `apply_sandbox_file(source_path, target_path, overwrite=False)` | 为 `/workspace/work` 内的单个文件创建写回审批申请，目标支持 `repo://...` 和 `shared://<name>/...`。 |

审批 API：

| 接口 | 说明 |
| --- | --- |
| `GET /api/approvals` | 查看当前会话审批记录。 |
| `POST /api/approvals/approve` | 批准审批。写回审批会执行写入；目录访问审批会记录 shared mount。body: `{"approval_id": "..."}`。 |
| `POST /api/approvals/reject` | 拒绝审批，body: `{"approval_id": "..."}`。 |

创建 pending approval 后，Web run 会进入 `awaiting_approval`，停止继续编排。用户批准或拒绝后，后端自动追加审批结果消息并继续运行。

启用方式：

```bash
AGENT_SANDBOX_IMAGE=python:3.12-slim
```

Windows 原生 PowerShell 示例：

```powershell
add_shared_mount("docs", "C:\Users\alice\Documents\docs", access="read") # 支持 "read"(只读, 默认) 或 "write"(读写)
```

容器启动参数会使用对应的 bind mount（只读挂载 `:ro` 或读写挂载 `:rw`）：

```text
C:\Users\alice\Documents\docs:/workspace/shared/docs:ro  # 只读
C:\Users\alice\Documents\docs:/workspace/shared/docs:rw  # 读写
```

注意不要授权敏感目录，例如 `AppData`、`C:\Windows`、`C:\Program Files`、`.ssh`、`.aws`、`.azure`、`.kube`。

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

`./run_web.sh` 和 `.\run_web.ps1` 会先运行 `python -m app.setup_auto`。该步骤只做启动前检查和用户确认后的依赖安装，不会替代前端的目录访问/写回审批机制。

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
