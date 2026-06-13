with open("/Users/zhaoyu/Documents/agent-framework/app/web_static/app.js", "r") as f:
    content = f.read()

old_ws = """  ws.addEventListener("message", (message) => {
    try {
      const payload = JSON.parse(message.data);
      if (payload.state) {
        renderState(payload.state);
      }
    } catch (error) {"""

new_ws = """  ws.addEventListener("message", (message) => {
    try {
      const payload = JSON.parse(message.data);
      if (payload.state) {
        renderState(payload.state);
      } else if (payload.type === "stream") {
        renderState({ model_output: (currentState.model_output || "") + (payload.content || "") });
      }
    } catch (error) {"""

content = content.replace(old_ws, new_ws)

with open("/Users/zhaoyu/Documents/agent-framework/app/web_static/app.js", "w") as f:
    f.write(content)
print("Patched ws")
