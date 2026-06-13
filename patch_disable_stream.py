import re

with open("/Users/zhaoyu/Documents/agent-framework/app/web_static/app.js", "r") as f:
    content = f.read()

old_ws = """      } else if (payload.type === "stream") {
        streamBuffer += (payload.content || "");
        if (!streamTimeout) {
          streamTimeout = setTimeout(() => {
            renderState({ model_output: (currentState.model_output || "") + streamBuffer }, true);
            streamBuffer = "";
            streamTimeout = null;
          }, 500);
        }
      }"""

new_ws = """      } else if (payload.type === "stream") {
        streamBuffer += (payload.content || "");
        // TEMPORARY TEST: DO NOT RENDER STREAM
        // if (!streamTimeout) {
        //   streamTimeout = setTimeout(() => {
        //     renderState({ model_output: (currentState.model_output || "") + streamBuffer }, true);
        //     streamBuffer = "";
        //     streamTimeout = null;
        //   }, 500);
        // }
      }"""

content = content.replace(old_ws, new_ws)

with open("/Users/zhaoyu/Documents/agent-framework/app/web_static/app.js", "w") as f:
    f.write(content)

print("Applied stream disable patch")
