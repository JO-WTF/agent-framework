# Orchestrator 设计说明

## 1. 模块位置

主要文件：

- `app/nodes/orchestrator.py`
- `app/nodes/common.py`
- `config/prompts.yaml` 的 `orchestrator`
- `app/memory/store.py` 的 context tag 工具函数

Orchestrator 是主图第一个节点，也是每次工具完成、Agent 阶段答复或 Evaluator 打回后的重新编排节点。

## 2. 职责边界

Orchestrator 负责：

- 判断任务复杂度：`simple` / `complex`。
- 为复杂任务生成和更新分级 `todo_list`。
- 识别当前任务需要的 `context_tags`。
- 给出期望下一步：`agent` 或 `evaluate`。
- 记录自己的 prompt、原始输出和可选 reasoning 内容，供 Web UI 调试。

Orchestrator 不负责：

- 直接回答用户问题。
- 执行工具。
- 修复工具参数。
- 判断最终回答内容是否合格。

设计意图是把“任务管理”从 Brain 中拆出。Brain 更擅长做下一步推理和行动，Orchestrator 更适合维护任务计划和状态。

## 3. 输入构造

`orchestrator_node()` 会先根据当前状态推断初始标签：

```python
initial_context_tags = infer_context_tags_from_state(state)[:4]
system_prompt = get_system_prompt("orchestrator", context_tags=initial_context_tags)
```

然后把以下内容交给 LLM：

- 当前任务复杂度。
- 可选上下文标签。
- 当前动态上下文标签由 system prompt 的 `【动态上下文标签】` 提供，user prompt 不重复携带。
- 当前 `todo_list` JSON。
- 最近消息摘要。

这样 Orchestrator 每次都能基于“旧计划 + 新证据”更新状态，而不是从零规划。

## 4. 输出协议

提示词要求只输出 JSON：

```json
{
  "task_complexity": "simple 或 complex",
  "next": "agent 或 evaluate",
  "context_tags": ["general"],
  "todo_list": [
    {
      "id": "1",
      "title": "任务标题",
      "status": "pending",
      "note": "当前进展或阻塞原因",
      "children": []
    }
  ]
}
```

代码用 `parse_json_object()` 解析，支持模型偶尔包一层 Markdown code block 或输出前后多余文本。

如果解析失败，Orchestrator 会保守回退：

- 保留原 `task_complexity`。
- 保留原 `todo_list`。
- 使用 `default_orchestrator_next(state)`。
- 使用初始推断的 `context_tags`。

## 5. todo 设计

todo item 必须包含：

| 字段 | 说明 |
| --- | --- |
| `id` | 层级编号，例如 `1`、`1.1`。 |
| `title` | 子任务名称。 |
| `status` | `pending`、`in_progress`、`completed`、`blocked`。 |
| `note` | 当前进展或阻塞原因。 |
| `children` | 子任务列表。 |

分级 todo 的设计是为了表达复杂任务中的包含关系。比如“更新架构文档”可以拆成：

```json
[
  {
    "id": "1",
    "title": "分析项目结构",
    "status": "completed",
    "note": "已读取 app、config、tests",
    "children": []
  },
  {
    "id": "2",
    "title": "更新文档",
    "status": "in_progress",
    "note": "正在补模块说明",
    "children": [
      {"id": "2.1", "title": "补 Brain 文档", "status": "completed", "note": "", "children": []},
      {"id": "2.2", "title": "补 Tools 文档", "status": "pending", "note": "", "children": []}
    ]
  }
]
```

Brain 后续会根据这个计划选择最小可执行子任务，Evaluator 也会用它检查是否还有未完成事项。

## 6. context_tags 设计

`context_tags` 用于按需加载上下文：

- `file_system`：文件、路径、目录相关。
- `command`：终端命令相关。
- `python`：Python 执行或 traceback。
- `tool_error`：工具失败经验。
- `web`：FastAPI、前端或浏览器控制台。
- `security`：权限、危险动作、安全约束。

Orchestrator 只能从可选标签中选择最多 4 个。这样可以限制系统 prompt 膨胀。

例子：用户说“读取这个文件并修复命令报错”，初始标签可能是：

```text
file_system, command, tool_error
```

`get_system_prompt()` 会用这些标签加载 `CLAUDE.md` 的相关片段和 Agent Notes，而不是加载全部规则。

## 7. 路由输出与代码校正

Orchestrator 输出 `next`，但代码会做最终校正：

```python
default_next = default_orchestrator_next(state)
next_node = "evaluate" if default_next == "evaluate" else "agent"
```

设计原因：LLM 可能错误地让工具结果或用户新消息进入 Evaluator。代码层只允许“最后一条消息是无 tool_calls 的 AIMessage”时进入质检。

因此 Orchestrator 的 `next` 是计划意图，不是绝对控制权。

## 8. 与其他模块的协作

- 与 Brain：Orchestrator 给计划，Brain 执行下一步。
- 与 Memory Manager：Orchestrator 输出先经 Memory Manager 固化到 `world_state`，再路由。
- 与 Tools：工具完成后回 Orchestrator 更新 todo，而不是直接让 Brain 总结。
- 与 Evaluator：质检打回后回 Orchestrator，把失败原因转成新计划。

## 9. 设计细节与风险

- 当前 Orchestrator 是 LLM 驱动，todo 更新质量取决于 prompt 和上下文。
- 解析失败会保守路由，但不会自动修复 todo JSON。
- `orchestrator_think` 会尝试提取 provider 的 `reasoning_content` 或 `<think>...</think>`，用于观察，不参与决策。
- 对简单任务，todo 可以为空；但只要任务涉及多步执行、调研、实现或验证，应生成 todo。
