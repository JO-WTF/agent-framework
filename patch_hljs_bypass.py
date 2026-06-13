import re

with open("/Users/zhaoyu/Documents/agent-framework/app/web_static/app.js", "r") as f:
    content = f.read()

old_logic = """    const canHighlight = window.hljs && language !== "text" && hljs.getLanguage(language);
    const highlighted = canHighlight
      ? hljs.highlight(String(text ?? ""), { language }).value
      : escapeHtml(text);"""

new_logic = """    const canHighlight = window.hljs && language !== "text" && hljs.getLanguage(language);
    const skipHighlight = currentState && currentState.status === "running";
    const highlighted = (canHighlight && !skipHighlight)
      ? hljs.highlight(String(text ?? ""), { language }).value
      : escapeHtml(text);"""

content = content.replace(old_logic, new_logic)

with open("/Users/zhaoyu/Documents/agent-framework/app/web_static/app.js", "w") as f:
    f.write(content)

print("Applied hljs bypass patch")
