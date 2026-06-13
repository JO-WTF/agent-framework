with open("/Users/zhaoyu/Documents/agent-framework/app/tools/geo.py", "r", encoding="utf-8") as f:
    content = f.read()

content = content.replace("            \n                        display_names", "            display_names")

with open("/Users/zhaoyu/Documents/agent-framework/app/tools/geo.py", "w", encoding="utf-8") as f:
    f.write(content)
