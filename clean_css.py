with open("/Users/zhaoyu/Documents/agent-framework/app/web_static/styles.css", "r") as f:
    content = f.read()

idx = content.find("/* Collapsed Runtime Panel */")
if idx != -1:
    content = content[:idx]
    with open("/Users/zhaoyu/Documents/agent-framework/app/web_static/styles.css", "w") as f:
        f.write(content.rstrip() + "\n")
    print("Cleaned CSS!")
else:
    print("Not found")
