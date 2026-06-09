# Agent Framework

这是一个基于 LangGraph、LangChain Tool Calling 和 OpenAI-compatible Chat API 的 Agent 框架。它把用户输入、任务编排、Agent Brain 推理、工具调用、运行期记忆和最终质量检查组织成一张可循环的状态图，适合用于项目分析、内部查询、数据处理、联网检索和命令行自动化。

## 架构文档

完整架构说明已经拆到以下文档：

- [架构总览](ARCHITECTURE.md)
- [Agent Brain 设计说明](docs/modules/brain.md)
- [Orchestrator 设计说明](docs/modules/orchestrator.md)
- [路由与状态图设计说明](docs/modules/routing.md)
- [Memory Manager 设计说明](docs/modules/memory-manager.md)
- [Tools 与工具执行子图设计说明](docs/modules/tools.md)
- [Skill Mechanism 技能机制设计说明](docs/modules/skills.md)
- [Evaluator 设计说明](docs/modules/evaluator.md)
- [入口、配置与运行期模块说明](docs/modules/runtime-and-entrypoints.md)
- [开发者上手指南](docs/development.md)
- [新增工具指南](docs/how-to-add-tool.md)
- [状态字段与消息协议](docs/state-and-message-contract.md)
- [测试策略](docs/testing.md)

## 核心模块

| 模块 | 文件 | 职责 |
| --- | --- | --- |
| CLI 入口 | `app/cli.py` | 构建 LangGraph 主图，维护命令行会话记忆。 |
| Web 控制台 | `app/web.py` / `app/web_static/` | 提供浏览器 UI、WebSocket 事件、停止任务和状态快照。 |
| Orchestrator | `app/nodes/orchestrator.py` | 判断复杂度、生成/更新分级 todo、识别动态上下文标签。 |
| Agent Brain | `app/nodes/agent.py` | 注入 prompt、todo 和 world_state，生成回答或 tool calls。 |
| Memory Manager | `app/nodes/memory_manager.py` | 固化 `world_state`、归档早期消息、统一主图路由。 |
| Tools | `app/tools/` / `app/nodes/tool_execution_subgraph.py` | 执行搜索、Python、命令工具，并处理失败分类、修复和归档。 |
| Evaluator | `app/nodes/evaluator.py` | 检查最终答复是否满足用户问题和 todo，必要时打回重做。 |
| 配置层 | `app/config.py` / `config/prompts.yaml` | 初始化 LLM、搜索客户端、状态结构和各节点提示词。 |

## 运行

1. 安装依赖：

```bash
pip install -r requirements.txt
```

2. 配置 `.env`，至少设置：

```bash
LLM_PROVIDER=openai
LLM_MODEL_NAME=gpt-4o-mini
LLM_API_KEY=...
TAVILY_API_KEY=...
```

3. 启动 CLI：

```bash
./run_cli.sh
```

4. 启动 Web 控制台：

```bash
./run_web.sh
```

## 测试

```bash
.venv/bin/python -m unittest discover -s tests
```

当前测试重点覆盖 Memory Manager 路由与归档、工具执行子图的失败修复和安全边界、动态上下文按标签懒加载。更多说明见 [测试策略](docs/testing.md)。
