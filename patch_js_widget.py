import re

with open("/Users/zhaoyu/Documents/agent-framework/app/web_static/app.js", "r") as f:
    content = f.read()

# Add parseMessageBlocksJS function before renderMessages
js_code = """
function parseMessageBlocksJS(content) {
  if (!content) return null;
  const blocks = [];
  const regex = /^[ \\t]*(`{3,}|~{3,})[ \\t]*widget[ \\t]*\\r?\\n([\\s\\S]*?)\\n[ \\t]*\\1[ \\t]*$/gm;
  let lastIndex = 0;
  let match;
  while ((match = regex.exec(content)) !== null) {
    const textBefore = content.substring(lastIndex, match.index);
    if (textBefore.trim()) blocks.push({ type: "text", content: textBefore.trim() });
    try {
      const payload = JSON.parse(match[2].trim());
      if (payload && payload.widget_type) {
        blocks.push({ type: "widget", widget_type: payload.widget_type, id: payload.id || "", props: payload.props || {} });
      } else {
        blocks.push({ type: "text", content: match[0] });
      }
    } catch (e) {
      blocks.push({ type: "text", content: match[0] });
    }
    lastIndex = regex.lastIndex;
  }
  const textAfter = content.substring(lastIndex);
  if (textAfter.trim()) blocks.push({ type: "text", content: textAfter.trim() });
  return blocks.some(b => b.type === "widget") ? blocks : null;
}

function renderMessages(messages, status, model_output) {"""

content = content.replace("function renderMessages(messages, status, model_output) {", js_code)

# Now replace the logic inside renderMessages
old_logic = """  const displayMessages = [...messages];
  if (status === "running" && model_output) {
    displayMessages.push({ role: "assistant", content: model_output });
  }"""

new_logic = """  const displayMessages = [...messages];
  if (status === "running" && model_output) {
    const parsedBlocks = parseMessageBlocksJS(model_output);
    if (parsedBlocks) {
      displayMessages.push({ role: "assistant", content: model_output, blocks: parsedBlocks });
    } else {
      displayMessages.push({ role: "assistant", content: model_output });
    }
  }"""

content = content.replace(old_logic, new_logic)

# Re-apply the cache buster increment just in case
content = content.replace("styles.css?v=5", "styles.css?v=6")
content = content.replace("app.js?v=5", "app.js?v=6")

with open("/Users/zhaoyu/Documents/agent-framework/app/web_static/app.js", "w") as f:
    f.write(content)

print("Patched app.js for real-time widget rendering!")
