# Agent Brain 设计说明

## 1. 模块位置

主要文件：

- `app/nodes/agent.py`
- `app/nodes/common.py`
- `config/prompts.yaml` 的 `agent_brain`
- `app/tools/registry.py`

`Agent Brain` 是真正负责“推理和行动”的节点，实现函数是 `agent_reasoning_node()`。

## 2. 职责边界

Agent Brain 只做三件事：

1. 根据系统提示词、最近消息、todo 和 `world_state` 理解当前该做什么。
2. 在需要外部信息或执行动作时生成 `tool_calls`。
3. 在不需要继续调用工具时生成自然语言答复。

它不负责：

- 判断任务是否复杂。这是 Orchestrator 的职责。
- 执行工具。这是 Tools Node 和工具执行子图的职责。
- 归档历史或压缩上下文。这是 Memory Manager 的职责。
- 判断最终答复是否合格。这是 Evaluator 的职责。

这个边界能减少单个 LLM 节点的职责混杂。Brain 专注“下一步行动”，其他节点负责计划、记忆、工具安全和验收。

## 3. 输入上下文构造

`agent_reasoning_node()` 构造的消息形态是：

```python
system_prompt = (
    get_system_prompt("agent_brain", context_tags=context_tags)
    + "\n\n【Orchestrator 任务计划】\n"
    + format_todo_context(state)
)
messages = [SystemMessage(content=system_prompt)] + trim_messages(state["messages"], session_id=session_id)
response = await llm_with_tools.ainvoke(messages, config)
```

关键输入包括：

- `agent_brain` 提示词：定义 Brain 的行动准则。
- `context_tags`：让 `get_system_prompt()` 按需加载 `CLAUDE.md` 静态规则和 Agent Notes。
- `todo_list`：告诉 Brain 当前任务计划和进度。
- `world_state`：告诉 Brain 已确认事实、工具摘要和最终答复摘要。
- `trim_messages()` 后的消息窗口：保留必要近因上下文，避免无限增长。

## 4. 工具绑定设计

`app/nodes/agent.py` 中：

```python
llm_with_tools = llm_client.bind_tools(AGENT_TOOLS)
```

`AGENT_TOOLS` 来自 `app/tools/registry.py`：

```python
AGENT_TOOLS = [search_web, start_sandbox, sandbox_status, stop_sandbox, add_shared_mount, apply_sandbox_file, list_tool_results, read_tool_result, run_python, run_command]
```

设计初衷是让 Brain 通过标准 tool calling 协议提出工具请求，而不是自己拼接命令结果。这样：

- LLM 只生成结构化 `tool_calls`。
- 工具执行、失败分类和结果归档由工具层接管。
- 父图可以根据 `AIMessage.tool_calls` 精确路由到 Tools Node。

例子：用户问“读取项目文件并总结模块”。Brain 不应该直接假设文件内容，而应该生成 `run_command({"command": "rg --files"})` 或类似工具调用。工具返回后，再由 Orchestrator 更新 todo，Brain 继续读关键文件。

如果工具返回“已保存为引用 tool-xxxx”，Brain 应调用 `read_tool_result(ref_id="tool-xxxx")` 读取归档内容，必要时分页，而不是为了绕过截断重复执行缩小输出的命令。

## 5. 与 Orchestrator 的协作

Orchestrator 把复杂任务拆成 todo 后，Brain 根据规则选择下一步：

- 优先处理 `in_progress`。
- 其次处理最小可执行的 `pending` 子任务。
- 如果 todo 还有必要项未完成，不应提前宣称完成。
- 如果缺信息，提出具体问题。

这种设计把“计划是否完整”交给 Orchestrator，把“当前怎么推进”交给 Brain。比如：

```text
todo:
- 1 分析结构 in_progress
- 2 更新文档 pending
- 3 验证 pending
```

Brain 应优先读文件和整理结构，而不是直接输出“文档已更新”。当工具执行完成后，Orchestrator 再把第 1 项标记为 completed，并推进第 2 项。

## 6. 与 Memory Manager 的协作

Brain 的输出永远先进入 Memory Manager：

- 若输出是 `AIMessage(tool_calls=...)`，Memory Manager 路由到 `tools`。
- 若输出是自然语言回答，Memory Manager 路由回 `orchestrator`，让 Orchestrator 决定是否进入 `evaluate`。

这样做的原因是同一个 `AIMessage` 在不同阶段含义不同。只有 Memory Manager 结合 `last_node="agent"` 和消息类型，才能稳定判断下一跳。

## 7. 设计细节与注意点

- `trim_messages()` 会保留工具调用邻接关系，避免 LangChain/OpenAI 工具协议要求被破坏。
- `get_system_prompt()` 会把当前时间注入全局提示词，适合处理“今天、最新”等时间敏感任务。
- 当前 Brain 使用全局 `llm_with_tools`，在进程启动时绑定工具。如果后续需要动态工具集，需要把绑定移动到请求级或节点级。
- Brain 本身不做 JSON 解析，避免把执行节点变成结构化控制节点；结构化控制由 Orchestrator 和工具子图承担。

## 8. 一个完整例子

用户请求：“分析当前项目结构并更新架构文档。”

1. Orchestrator 生成 todo：扫描结构、读关键模块、更新文档、验证。
2. Brain 看到第一项 `in_progress`，调用 `run_command` 列文件。
3. Tools 返回文件清单。
4. Memory Manager 固化工具摘要。
5. Orchestrator 更新 todo，要求继续读关键文件。
6. Brain 调用更多只读命令读取 `app/nodes/`、`app/tools/`。
7. 文档更新完成后，Brain 给出最终说明。
8. Evaluator 检查 todo 是否都完成、回答是否提到实际更新结果。
