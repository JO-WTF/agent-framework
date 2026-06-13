with open("/Users/zhaoyu/Documents/agent-framework/app/tools/registry.py", "r", encoding="utf-8") as f:
    content = f.read()

old_code = """GENERAL_AGENT_TOOL_CATEGORIES = ("search", "sandbox", "results", "execution", "skills")"""
new_code = """GENERAL_AGENT_TOOL_CATEGORIES = ("search", "sandbox", "results", "execution", "skills", "geo", "visualization")"""

content = content.replace(old_code, new_code)

with open("/Users/zhaoyu/Documents/agent-framework/app/tools/registry.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Patched registry.py")
