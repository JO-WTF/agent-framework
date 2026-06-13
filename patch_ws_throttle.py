import re

with open("/Users/zhaoyu/Documents/agent-framework/app/web_static/app.js", "r") as f:
    content = f.read()

old_ws = """  ws.addEventListener("message", (message) => {
    try {
      const payload = JSON.parse(message.data);
      if (payload.state) {
        renderState(payload.state);
      } else if (payload.type === "stream") {
        renderState({ model_output: (currentState.model_output || "") + (payload.content || "") }, true);
      }
    } catch (error) {"""

new_ws = """
  let streamBuffer = "";
  let streamTimeout = null;

  ws.addEventListener("message", (message) => {
    try {
      const payload = JSON.parse(message.data);
      if (payload.state) {
        renderState(payload.state);
      } else if (payload.type === "stream") {
        streamBuffer += (payload.content || "");
        if (!streamTimeout) {
          streamTimeout = setTimeout(() => {
            renderState({ model_output: (currentState.model_output || "") + streamBuffer }, true);
            streamBuffer = "";
            streamTimeout = null;
          }, 100);
        }
      }
    } catch (error) {"""

if "let streamBuffer =" not in content:
    content = content.replace(old_ws, new_ws.strip())

with open("/Users/zhaoyu/Documents/agent-framework/app/web_static/app.js", "w") as f:
    f.write(content)

print("Applied WS throttle")
