# Evaluator 设计说明

## 1. 模块位置

主要文件：

- `app/nodes/evaluator.py`
- `app/cli.py` 的 `route_after_evaluation()`
- `config/prompts.yaml` 的 `evaluator`

Evaluator 是主图的最终质量检查节点。

## 2. 设计初衷

复杂任务中，Agent 生成自然语言回答不代表任务真的完成。常见问题包括：

- todo 里还有 `pending` 或 `in_progress` 项，但回答声称已经完成。
- 工具失败后，回答用“无法获取”搪塞，而不是重新规划。
- 用户要求调研或验证，但回答没有引用工具结果。
- 被质检打回后没有针对缺失项继续执行。

Evaluator 用独立 LLM 调用审查草稿回答，相当于一个轻量 QA gate。

## 3. 输入构造

`evaluate_response_node()` 会构造：

- 最近一个用户问题。
- Orchestrator todo 状态，来自 `format_todo_context(state)`。
- 最近上下文摘要，来自 `summarize_recent_messages()`。
- Agent 草稿答复。

然后使用 `get_system_prompt("evaluator", context_tags=...)` 调用 LLM。

提示词要求只输出：

```text
PASS
```

或：

```text
REJECT: <缺失原因>
```

## 4. 打回机制

如果结果以 `REJECT` 开头：

```python
reject_msg = HumanMessage(
    content=f"[质检打回] 回答不合格！原因：{reason}。请参考 todo list 重新规划下一步，并重新调用必要工具获取数据。"
)
return {
    "eval_status": "REJECT",
    "revision_count": rev_count + 1,
    "messages": [reject_msg],
    "last_node": "evaluate",
}
```

下一跳由 `route_after_evaluation()` 送回 Orchestrator，而不是直接回 Brain。这样 Orchestrator 可以把打回原因体现在 todo 状态里。

例子：

1. todo 里“运行测试”还是 `pending`。
2. Agent 回答“文档已更新完成”。
3. Evaluator 返回 `REJECT: 未验证测试或文档一致性`。
4. 系统追加 `[质检打回]` 消息。
5. Orchestrator 重新规划，把验证项设为 `in_progress`。
6. Brain 调用命令运行测试。

## 5. 熔断设计

`revision_count >= 3` 时强制 `PASS`：

```python
if rev_count >= 3:
    return {"eval_status": "PASS", "last_node": "evaluate"}
```

设计原因：Evaluator 本身也是 LLM，可能误判或与 Brain 形成循环。三次打回已经足够暴露问题，再继续自动循环会浪费调用成本，并可能卡住用户。

这不是表示结果一定完美，而是系统层面的停止条件。最终答复应说明如果还有未完成事项或无法验证的内容。

## 6. 与 todo 的关系

Evaluator 的核心判断依据不是“回答写得好不好”，而是“回答是否满足任务计划”。因此 `format_todo_context()` 会把：

- `task_complexity`
- `context_tags`
- `world_state`
- `todo_list`

一起给 Evaluator。

如果 todo 中还有必要事项未完成，Evaluator 应打回。这个设计让 Orchestrator 的计划真正参与验收，而不是只用于前端展示。

## 7. 局限

- Evaluator 只能基于当前上下文和 `world_state` 判断，不能自动读取外部文件。
- 如果 Orchestrator 的 todo 本身漏项，Evaluator 也可能漏检。
- 如果模型输出没有严格以 `REJECT` 开头，代码会按通过处理。
- 熔断后可能带着残余风险结束。

后续可改进方向：

- 使用结构化 JSON 输出替代字符串前缀。
- 将严重问题分级，例如 `REJECT_RETRYABLE` 与 `REJECT_NEEDS_USER`。
- 对特定任务接入确定性检查器，例如测试结果、文件 diff、链接可达性。
