# 测试策略

## 1. 测试目标

本项目大量行为由 LLM prompt 驱动，因此测试重点不是断言模型一定输出什么，而是保护代码层协议和安全边界：

- 主图路由不能乱跳。
- Memory Manager 不能破坏消息协议。
- 工具子图不能无限重试或自动扩大风险。
- 动态上下文必须按标签懒加载。
- 缺依赖等外部动作不能被子图擅自执行。

## 2. 运行测试

推荐：

```bash
.venv/bin/python -m unittest discover -s tests
```

如果虚拟环境安装了 pytest：

```bash
.venv/bin/python -m pytest tests
```

不推荐直接使用系统 Python，因为它可能没有安装项目依赖。

## 3. 现有测试

### `tests/test_memory_manager.py`

覆盖：

- `build_world_state()` 是否捕获 `task_complexity`、`context_tags`、`todo_list` 和工具结果摘要。
- `memory_manager_node()` 是否只在状态已固化后归档早期消息。
- 归档时是否返回 `RemoveMessage`。
- `route_after_memory()` 是否依赖 `last_node`。

保护的设计边界：记忆压缩不能早于事实固化，路由不能只靠最后消息类型猜。

### `tests/test_tool_execution_subgraph.py`

覆盖：

- 单工具子图能执行工具。
- 父图 Tools Node 只返回 `ToolMessage`，不暴露内部历史。
- 未知工具返回失败消息。
- session_id 能写入工具上下文。
- 工具异常能被捕获。
- Python 缺依赖返回 `needs_external_action`。
- retryable failure 能调用修复器并重试。
- 危险命令修复会被拒绝。

保护的设计边界：工具自动修复只能修参数，不能越权执行外部动作。

### `tests/test_dynamic_context.py`

覆盖：

- `STATIC_GUIDELINES.md` 静态规则按 `context_tags` 筛选。
- Agent Notes 按标签筛选。
- `get_system_prompt()` 会注入动态标签、规则和笔记。
- 可从消息内容启发式推断标签。

保护的设计边界：上下文按需加载，避免 prompt 无限膨胀。

## 4. 新增测试的优先级

### 高优先级

- 改 `route_after_memory()`。
- 改 `AgentState` 字段。
- 改 `trim_messages()` 或归档逻辑。
- 改工具执行子图失败分类。
- 新增有副作用工具。
- 修改 tool call / ToolMessage 生成逻辑。

### 中优先级

- 改 prompt 输出 JSON schema。
- 改 Web 事件状态字段。
- 改 `world_state` 内容。
- 新增 context tag。

### 低优先级

- 纯文档。
- 日志文案。
- 不影响协议的样式调整。

## 5. 测试 LLM 相关逻辑

不要依赖真实 LLM 输出。优先使用 fake class 或 `unittest.mock.patch`。

示例：

```python
class FakeLLM:
    async def ainvoke(self, messages, config=None):
        return AIMessage(
            content='{"can_retry": true, "args": {"code": "print(1)"}, "reason": "修复"}'
        )

with patch("app.nodes.tool_execution_subgraph.llm_client", FakeLLM()):
    ...
```

这样测试只验证代码如何处理模型输出，而不是验证模型能力。

## 6. 测试工具子图

工具子图测试建议覆盖四类：

1. `success`：正常返回。
2. `retryable_failure`：进入 fix，再重试。
3. `terminal_failure`：不重试，直接 finalize。
4. `needs_external_action`：不进入 fix，返回建议动作。

如果新增工具有自己的失败格式，应为 `classify_tool_result()` 增加直接单元测试。

## 7. 测试 Memory Manager

修改记忆逻辑时至少验证：

- `world_state` 是否保留必要事实。
- 未固化状态不会归档。
- 已固化状态会归档冗余早期消息。
- 归档后不会留下孤立开头 `ToolMessage`。
- `tool_results` 不会无限增长。

## 8. 测试路由

路由测试应构造最小状态，不需要跑完整图。

关键组合：

| `last_node` | 最后消息 | 期望 |
| --- | --- | --- |
| `agent` | `AIMessage(tool_calls)` | `tools` |
| `agent` | final `AIMessage` | `orchestrator` |
| `tools` | `ToolMessage` | `orchestrator` |
| `orchestrator` | final `AIMessage` + `orchestrator_next=evaluate` | `agent`（Memory 不直达 Evaluator） |
| `orchestrator` | `HumanMessage` | `agent` |

## 9. 测试新增工具

新增工具建议至少有：

- 直接调用工具函数的成功测试。
- Tools Node 通过 tool call 调用该工具的测试。
- 工具失败输出的分类测试。
- 长输出归档测试。
- 风险参数测试。

如果工具访问网络或外部服务，默认 mock 外部客户端，不让单元测试依赖真实网络。

## 10. 测试失败排查

常见问题：

- `ModuleNotFoundError: langchain_core`：使用了系统 Python，改用 `.venv/bin/python`。
- `No module named pytest`：虚拟环境没有 pytest，使用 `unittest discover` 或安装 pytest。
- LLM/Tavily key 报错：单元测试应设置 dummy env 或 mock 客户端。
- 工具命令超时：检查测试命令是否可在 30 秒内完成。
- JSON 解析失败：fake LLM 输出必须是合法 JSON 字符串。

## 11. 提交前检查

```bash
.venv/bin/python -m unittest discover -s tests
git status --short
```

如果改了文档之外的代码，说明测试覆盖了哪些行为，以及哪些没有覆盖。
