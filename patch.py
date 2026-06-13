import re

with open("/Users/zhaoyu/Documents/agent-framework/app/web.py", "r") as f:
    content = f.read()

# Find index route
old_index = """@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")"""

new_index = """@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache, no-store, must-revalidate"})"""

if old_index in content:
    with open("/Users/zhaoyu/Documents/agent-framework/app/web.py", "w") as f:
        f.write(content.replace(old_index, new_index))
    print("Patched!")
else:
    print("Not found")
