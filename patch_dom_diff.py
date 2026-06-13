import re

with open("/Users/zhaoyu/Documents/agent-framework/app/web_static/app.js", "r") as f:
    content = f.read()

start = content.find("if (!displayMessages.length) {")
end = content.find("  hydrateWidgets(els.messageList);", start)

old_logic = content[start:end+34]

new_logic = """  if (!displayMessages.length) {
    els.messageList.innerHTML = `<div class="empty">暂无对话</div>`;
    return;
  }

  if (els.messageList.children.length === 1 && els.messageList.children[0].classList.contains("empty")) {
    els.messageList.innerHTML = "";
  }

  const currentNodes = Array.from(els.messageList.children);

  for (let i = 0; i < displayMessages.length; i++) {
    const msg = displayMessages[i];
    const role = escapeHtml(msg.role || "assistant");
    const sig = JSON.stringify({ role: msg.role, blocks: msg.blocks || null, content: msg.content || "" });
    
    let node = currentNodes[i];
    if (node && node.dataset.sig === sig) {
      continue;
    }
    
    const inner = role === "assistant" 
      ? renderAssistantBlocks(messageBlocks(msg)) 
      : escapeHtml(String(msg.content || ""));

    if (!node) {
      node = document.createElement("div");
      els.messageList.appendChild(node);
    }
    
    node.className = `message ${role}`;
    node.dataset.sig = sig;
    node.innerHTML = inner;
    hydrateWidgets(node);
  }

  // Remove excess nodes
  for (let i = displayMessages.length; i < currentNodes.length; i++) {
    if (currentNodes[i] && currentNodes[i].parentNode) {
      currentNodes[i].parentNode.removeChild(currentNodes[i]);
    }
  }
"""

content = content.replace(old_logic, new_logic)

with open("/Users/zhaoyu/Documents/agent-framework/app/web_static/app.js", "w") as f:
    f.write(content)

print("Applied DOM Diffing")
