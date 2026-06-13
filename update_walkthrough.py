import re

with open("/Users/zhaoyu/.gemini/antigravity/brain/5fa9039f-2e86-420e-89b7-a537a1881b77/walkthrough.md", "r") as f:
    content = f.read()

new_content = content + """
## 2026-06-13 UX 状态反馈优化 (v25)

针对任务在调度、检索等阶段“静默运行”导致用户误以为卡死的问题，在主聊天界面新增了**动态运行状态指示器**：
- 当 `status === "running"` 时，聊天框末尾会生成一个带有 Loading Spinner 的特殊气泡。
- 该气泡会实时同步读取后台 Event 队列中最新的一条事件标题（例如：“任务编排与分析中 (Orchestrator)”、“工具执行中”等）。
- 无缝衔接：一旦最终的大模型开始吐字，系统状态指示器会自动伴随内容生成，使用户能够全程掌握后台动向。
"""

with open("/Users/zhaoyu/.gemini/antigravity/brain/5fa9039f-2e86-420e-89b7-a537a1881b77/walkthrough.md", "w") as f:
    f.write(new_content)

print("Updated walkthrough")
