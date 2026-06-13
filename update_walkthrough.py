import re

with open("/Users/zhaoyu/.gemini/antigravity/brain/5fa9039f-2e86-420e-89b7-a537a1881b77/walkthrough.md", "r") as f:
    content = f.read()

new_content = content + """
6. **根除全量状态广播**：修复了后端在每个 Token 输出时都会附带发送整个 Session 全量状态的逻辑漏洞，彻底解除了前端在流式输出时的网络传输与全页面强制重绘瓶颈。
"""

with open("/Users/zhaoyu/.gemini/antigravity/brain/5fa9039f-2e86-420e-89b7-a537a1881b77/walkthrough.md", "w") as f:
    f.write(new_content)

print("Updated walkthrough")
