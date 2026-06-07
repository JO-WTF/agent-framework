# Agent Framework 改进计划

## 目标
将当前架构的安全、状态管理、编排效率、工具鲁棒性与 Web 并发能力拆成可断开、可逐步实施的任务。每个任务应包含明确的目标、具体执行步骤和验收标准，便于后续逐个完成并追踪改造进度。

## 关联文档
- 主架构说明：`ARCHITECTURE.md`
- 详细改进计划：本文件

## 阶段 1：安全隔离与工具约束

### 任务 1.1：`run_command` 安全改造

目标
- 禁止模型直接通过 shell 执行任意命令，避免恶意命令破坏主机系统。

执行步骤
1. 在 `app/tools/registry.py` 中替换 `subprocess.run(command, shell=True, ...)` 为 `subprocess.run(args_list, shell=False, ...)`。
2. 设计并实现命令白名单，例如只允许 `ls`, `cat`, `echo`, `python` 等安全命令。
3. 为 `run_command` 添加输入检查，拒绝包含 `|`, `&&`, `;`, `>`、重定向、管道、子 shell 等危险符号。
4. 添加默认超时和输出限制：
   - 超时 10-20 秒
   - 最大输出 10 KB
5. 编写测试用例：
   - 合法命令成功执行
   - 危险命令被拒绝
   - 超时命令被终止

验收标准
- `run_command` 仅执行白名单命令
- 所有危险模式返回错误提示而不执行
- 超时和输出限制生效

### 任务 1.2：`run_python` 沙箱化执行

目标
- 避免直接在主进程中 `exec(code, namespace)`，限制模型执行的 Python 代码能力。

执行步骤
1. 用独立子进程或线程池运行 Python 代码，避免阻塞主事件循环和泄露当前进程状态。
2. 构建最小执行环境：
   - 禁止直接访问 `os.environ`、`sys.modules`、`open()` 等敏感接口
   - 禁止网络访问、文件写入到非临时目录
   - 限定可导入模块集合，例如 `math`, `json`, `csv`, `numpy`（可选）
3. 添加执行超时与输出限制：
   - 超时 10-20 秒
   - 最大 stdout/stderr 10 KB
4. 如果沙箱无法实施，可先实现"安全模式"：仅允许读取输入并返回计算结果，禁止写文件和调用系统命令。
5. 编写测试：
   - 普通计算成功
   - 访问敏感变量失败
   - 死循环/超时失败

验收标准
- `run_python` 不再直接修改主进程环境
- 代码调用受限在安全沙箱内
- 超时和输出限制生效

### 任务 1.3：工具输入与输出过滤

目标
- 规范工具输入参数，防止 Prompt Injection 引入恶意命令。

执行步骤
1. 在 `app/tools/` 或 `app/nodes/` 工具调用入口加入参数检测。
2. 定义危险模式黑名单，例如 `rm -rf`, `ssh`, `curl | sh`, `base64 -d`, `eval`, `exec`。
3. 对 `run_python` 和 `run_command` 返回结果进行清洗：
   - 剪裁过长文本
   - 删除命令行提示符和堆栈追踪中的敏感路径
4. 如果检测到可疑内容，返回统一错误对象而非原始 traceback。

验收标准
- 所有工具输入经过过滤
- 输出超过阈值时只返回摘要
- 所有异常返回结构化错误信息

## 阶段 2：状态裁剪与记忆管理

### 任务 2.1：实现消息窗口机制 ✅ 已完成

**状态**：✅ 完成于 2026-06-07

目标 ✅
- 防止 `messages` 随会话无限增长，控制 LLM 上下文大小。

实现细节 ✅
- `app/memory/store.py` 中 `trim_messages()` 默认保留最近 8 条消息
- `app/nodes/` 所有主节点改用裁剪后的上下文
- 工具结果超过 1 KB 时生成摘要 + 引用 ID
- 工具输出存储到 `tool_results.json`，模型仅收到引用

验收标准 ✅
- 仅使用裁剪后的上下文调用模型
- 对话历史不会无限膨胀
- 关键上下文仍在任务执行中可用

### 任务 2.2：静态全局提示注入 ✅ 已完成

**状态**：✅ 完成于 2026-06-07

目标 ✅
- 为所有节点提供一致的系统提示和指导原则

实现细节 ✅
- 创建 `CLAUDE.md` 作为静态全局提示
- `app/memory/store.py` 中 `load_static_guidelines()` 加载 CLAUDE.md
- 所有节点调用 `get_system_prompt()` 获取完整系统提示（静态指导 + 节点特定提示）

验收标准 ✅
- 所有节点使用一致的系统提示
- CLAUDE.md 被正确注入到模型上下文
- 多用户环境下提示正确隔离

## 阶段 3：编排频次与循环优化

### 任务 3.1：Orchestrator 触发优化

目标
- 减少 Orchestrator 的不必要调用，尤其是在简单工具执行后。

执行步骤
1. 在 `AgentState` 中新增 `last_tool_processed`、`orchestrator_needed` 字段。
2. 修改 `tools` 节点执行流程：
   - 只有当工具结果导致 `todo_list` 实际变化时，才将 `orchestrator_needed` 置为 `true`。
   - 否则直接返回给 Agent 或终止当前动作。
3. 修改 `route_after_orchestration` 和 `should_continue`：
   - 如果 `Agent` 无工具调用且当前结果已满足任务，直接进入 `evaluate`。
   - 如果 `tools` 结果未触发 `todo` 变化，则跳过 Orchestrator，避免重复评估。
4. 编写测试：
   - 简单任务不再多次调用 Orchestrator
   - `todo_list` 变化时仍会正确触发重新评估

验收标准
- 工具执行后只有必要时才触发 Orchestrator
- 简单任务开销显著减少

### 任务 3.2：错误与重试保护

目标
- 防止"工具报错 → 修复 → 再次报错"的无效循环。

执行步骤
1. 在 `AgentState` 中新增：
   - `tool_error_count`
   - `task_retry_count`
   - `last_error_type`
2. 在 `tools_execution_node` 中捕获错误并记录状态。
3. 在 `orchestrator_node` 或 `agent_reasoning_node` 中判断：
   - 同一工具连续失败 2 次以上，将当前子任务标记为 `blocked`。
   - 如果总步骤超过阈值（例如 12 次），直接提示用户介入。
4. 编写测试：
   - 连续错误后任务进入 `blocked`
   - 总步骤阈值触发返回用户

验收标准
- 连续工具失败不会导致无限循环
- 失败后任务进入可用户干预的状态

## 阶段 4：工具数据通道与鲁棒性提升

### 任务 4.1：共享数据通道设计

目标
- 引入 Document Store 作为工具结果的共享中间数据对象，避免大输出在 `messages` 中传递。

执行步骤
1. 设计 `tool_result_store` 或 `document_store`，包含：
   - `store_tool_result(tool_name, raw_output, metadata)`
   - `get_tool_summary(reference_id)`
   - `get_tool_content(reference_id)`
2. 修改工具输出格式，使其返回：
   - `status`
   - `summary`
   - `reference_id`
   - `metadata`
3. 在 `config/prompts.yaml` 中增加说明，指导模型使用 `reference_id` 查询数据，而不是直接要求完整结果。
4. 为常见格式增加提取器：
   - CSV 提取列名、行数、摘要结果
   - JSON 提取键结构和字段说明
   - 日志提取错误摘要和时间范围
5. 编写测试：
   - 工具结果正确写入 Document Store
   - 引用 ID 可用于还原和摘要
   - 提取器输出正确

验收标准
- 通过引用 ID 能访问工具结果
- 模型上下文仅包含摘要信息
- 各类大数据类型被正确提取

### 任务 4.2：统一工具错误返回格式

目标
- 让后续节点处理错误更稳定，避免原始 traceback 干扰模型推理。

执行步骤
1. 定义统一工具结果 schema：
   - `status`: `success` / `failure`
   - `summary`
   - `reference_id`
   - `error_type`: `timeout` / `syntax_error` / `external_failure` / `security_rejected`
   - `details`（可选）
2. 修改 `app/tools/registry.py` 所有工具函数，返回该 schema。
3. 在 `app/nodes/` 中新增错误分类逻辑，将 `failure` 转换为：
   - 具体问题描述
   - 推荐下一步动作
   - 是否需要用户确认
4. 为 `search_web` 和 `run_command` 增加重试策略：
   - 网络失败重试一次
   - 失败后返回可控错误信息而不是原始异常
5. 编写测试：
   - 错误格式统一
   - `failure` 结果能被 Agent 正确解析
   - 重试机制工作

验收标准
- 工具错误返回一致
- 节点不会将 traceback 直接传给模型
- 常见错误可被语义化处理

## 阶段 5：并发与 Web 架构改造

### 任务 5.1：多会话隔离与状态管理 ✅ 已完成

**状态**：✅ 完成于 2026-06-07

目标 ✅
- 支持多用户并发访问，避免单例 `ConsoleSession` 导致状态冲突。

实现细节 ✅
- `app/web.py` 新增 `SessionManager` 管理多个 `ConsoleSession` 实例
- 通过 `session_id` 绑定 API 请求和 WebSocket 连接
- 每个 `ConsoleSession` 保留独立的 `thread_id`、`memory_messages`、`state`、`running_task`
- 前端通过 `localStorage` 维护 `session_id`，每次请求都发送给后端

已完成项 ✅
- 多会话并发支持
- 不同会话的状态完全隔离
- WebSocket 连接稳定性修复（修复了 `ConsoleSession.snapshot()` 和回调参数问题）

待实现项 ⏳
- 会话空闲超时清理
- 会话恢复机制

### 任务 5.2：I/O 友好与并发保护

目标
- 避免工具执行或长时间任务阻塞 FastAPI 事件循环。

执行步骤
1. 将 `run_python` 移入线程池或子进程执行。
2. 保证 `run_command` 使用 `asyncio` 执行器，带超时取消。
3. 为 WebSocket 和 HTTP 接口添加请求超时和并发限制。
4. 在 `ConsoleSession` 中增加任务取消入口，允许用户中断当前运行。
5. 编写测试：
   - 工具执行不阻塞其他请求
   - 超时任务被取消
   - WebSocket 连接稳定

验收标准
- 服务仍可响应其他请求，即使有会话在运行工具
- 超时和取消工作正常
- 并发请求不会导致全局阻塞

## 完成度统计

- ✅ 已完成：3 个主要任务
  - 2.1 消息窗口机制
  - 2.2 静态全局提示注入
  - 5.1 多会话隔离（基础）

- ⏳ 进行中/部分完成：0 个任务

- 📋 待实现：3 个主要阶段 + 子任务
  - 阶段 1：安全隔离（1.1, 1.2, 1.3）
  - 阶段 3：编排优化（3.1, 3.2）
  - 阶段 4：工具数据通道（4.1, 4.2）
  - 阶段 5.1：会话生命周期管理
  - 阶段 5.2：I/O 友好与并发保护

## 建议优先级

1. 安全隔离（阶段 1）- 应尽快实施
2. 文档存储完善（已完成基础）
3. 会话生命周期管理（阶段 5.1 续）
4. Orchestrator 循环优化（阶段 3）
5. 工具数据通道与鲁棒性（阶段 4）
6. I/O 并发保护（阶段 5.2）

## 最近修复

- **2026-06-07**: 修复 `app/web.py` 中 `run_agent()` 的回调参数拼写错误 (`sessionsession` → `session`)
- **2026-06-07**: 完成 WebSocket 会话隔离，每个浏览器用户获得独立的 `ConsoleSession` 和事件流
- **2026-06-07**: 实现后端事件发布机制，所有模型和工具更新通过 WebSocket 实时流向前端

## 执行建议

- 阶段 1.1：先实现 `run_command` 的安全白名单与超时，再改造 `run_python`。
- 阶段 2.1-2.2：已完成，确保后续节点都使用裁剪后的上下文。
- 阶段 3.1：先实现简单任务快速路径，再观察 Orchestrator 调用次数是否下降。
- 阶段 4.1：先实现 `summary + reference_id` 机制，确保现有工具不会因大输出崩溃。
- 阶段 5.1：已实现多会话基础，建议后续完成会话生命周期管理。
- 阶段 5.2：建议在并发改进前，确保现有 WebSocket 连接稳定（已修复）。

## 注意事项

- 每个阶段完成后补充单元测试或集成验证，尤其是工具安全和会话隔离场景。
- 在调整 `messages` 窗口时，保留关键上下文与 `todo_list` 追踪状态，避免模型失去任务记忆。
- 在引入持久化存储之前，先保留可回退的本地/内存方案，避免过早耦合外部数据库。
