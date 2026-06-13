import re

with open("/Users/zhaoyu/Documents/agent-framework/app/web_static/app.js", "r") as f:
    content = f.read()

# 1. parseMessageBlocksJS
parse_msg_code = """
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
"""
if "function parseMessageBlocksJS" not in content:
    content = content.replace("let lastMessagesSignature = null;", parse_msg_code + "\nlet lastMessagesSignature = null;")

# 2. Modify renderMessages signature
content = content.replace("function renderMessages(messages) {", "function renderMessages(messages, status, model_output) {")

# 3. Modify renderMessages logic
old_logic = "const displayMessages = [...messages];"
new_logic = """const displayMessages = [...messages];
  if (status === "running" && model_output) {
    const parsedBlocks = parseMessageBlocksJS(model_output);
    if (parsedBlocks) {
      displayMessages.push({ role: "assistant", content: model_output, blocks: parsedBlocks });
    } else {
      displayMessages.push({ role: "assistant", content: model_output });
    }
  }"""
if "const parsedBlocks = parseMessageBlocksJS(model_output);" not in content:
    content = content.replace(old_logic, new_logic)

# 4. Modify renderState to pass status and model_output
content = content.replace("renderMessages(state.messages || []);", "renderMessages(state.messages || [], status, state.model_output);")

# 5. Patch ws.addEventListener
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
if "payload.type === \"stream\"" not in content:
    content = content.replace(old_ws, new_ws)

with open("/Users/zhaoyu/Documents/agent-framework/app/web_static/app.js", "w") as f:
    f.write(content)

print("Applied realtime widget rendering!")
