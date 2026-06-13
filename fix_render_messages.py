import re

with open("/Users/zhaoyu/Documents/agent-framework/app/web_static/app.js", "r") as f:
    content = f.read()

# Replace renderMessages entirely
start_idx = content.find("function renderMessages(messages, status, model_output) {")
if start_idx == -1:
    start_idx = content.find("function renderMessages(messages) {")

if start_idx != -1:
    end_idx = content.find("function hydrateWidgets(root) {", start_idx)
    old_render = content[start_idx:end_idx]
    
    new_render = """function renderMessages(messages, status, model_output) {
  const displayMessages = [...messages];
  if (status === "running" && model_output) {
    const parsedBlocks = parseMessageBlocksJS(model_output);
    if (parsedBlocks) {
      displayMessages.push({ role: "assistant", content: model_output, blocks: parsedBlocks });
    } else {
      displayMessages.push({ role: "assistant", content: model_output });
    }
  }

  const signature = JSON.stringify(
    displayMessages.map((m) => ({ role: m.role, blocks: m.blocks || null, content: m.content || "" }))
  );
  if (signature === lastMessagesSignature) return;
  lastMessagesSignature = signature;

  const isAtBottom = els.messageList.scrollHeight - els.messageList.scrollTop - els.messageList.clientHeight <= 50;

  if (!displayMessages.length) {
    els.messageList.innerHTML = `<div class="empty">暂无对话</div>`;
    return;
  }

  els.messageList.innerHTML = displayMessages
    .map((msg) => {
      const role = escapeHtml(msg.role || "assistant");
      const sig = JSON.stringify({ role: msg.role, blocks: msg.blocks || null, content: msg.content || "" });
      
      const inner = role === "assistant" 
        ? renderAssistantBlocks(messageBlocks(msg)) 
        : escapeHtml(String(msg.content || ""));
        
      return `<div class="message ${role}" data-sig='${escapeHtml(sig)}'>${inner}</div>`;
    })
    .join("");

  hydrateWidgets(els.messageList);

  if (isAtBottom) {
    els.messageList.scrollTop = els.messageList.scrollHeight;
  }
}

"""
    content = content.replace(old_render, new_render)
    
    with open("/Users/zhaoyu/Documents/agent-framework/app/web_static/app.js", "w") as f:
        f.write(content)
    print("Fixed renderMessages successfully!")
else:
    print("Could not find renderMessages")
