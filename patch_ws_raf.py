import re

with open("/Users/zhaoyu/Documents/agent-framework/app/web_static/app.js", "r") as f:
    content = f.read()

old_ws = """        streamBuffer += (payload.content || "");
        if (!streamTimeout) {
          streamTimeout = setTimeout(() => {
            renderState({ model_output: (currentState.model_output || "") + streamBuffer }, true);
            streamBuffer = "";
            streamTimeout = null;
          }, 100);
        }"""

new_ws = """        streamBuffer += (payload.content || "");
        if (!streamTimeout) {
          streamTimeout = requestAnimationFrame(() => {
            renderState({ model_output: (currentState.model_output || "") + streamBuffer }, true);
            streamBuffer = "";
            streamTimeout = null;
          });
        }"""

content = content.replace(old_ws, new_ws)

with open("/Users/zhaoyu/Documents/agent-framework/app/web_static/app.js", "w") as f:
    f.write(content)

print("Applied WS RAF throttle")
