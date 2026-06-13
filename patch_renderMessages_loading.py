import re

with open("/Users/zhaoyu/Documents/agent-framework/app/web_static/app.js", "r") as f:
    content = f.read()

old_logic = """  if (status === "running" && model_output) {
    const combinedRound = model_output.replace(/\\n*\\[\\[MODEL_OUTPUT_ROUND_BREAK\\]\\]\\n*/g, "\\n\\n").trim();
    if (combinedRound) {
      const parsedBlocks = parseMessageBlocksJS(combinedRound);
      if (parsedBlocks) {
        displayMessages.push({ role: "assistant", content: combinedRound, blocks: parsedBlocks });
      } else {
        displayMessages.push({ role: "assistant", content: combinedRound });
      }
    }
  }

  const signature = JSON.stringify("""

new_logic = """  if (status === "running") {
    if (model_output) {
      const combinedRound = model_output.replace(/\\n*\\[\\[MODEL_OUTPUT_ROUND_BREAK\\]\\]\\n*/g, "\\n\\n").trim();
      if (combinedRound) {
        const parsedBlocks = parseMessageBlocksJS(combinedRound);
        if (parsedBlocks) {
          displayMessages.push({ role: "assistant", content: combinedRound, blocks: parsedBlocks });
        } else {
          displayMessages.push({ role: "assistant", content: combinedRound });
        }
      }
    }
    
    // Append a loading status indicator
    const lastEvent = currentState.events && currentState.events.length > 0 ? currentState.events[currentState.events.length - 1] : null;
    let loadingText = "处理中";
    if (lastEvent && lastEvent.title) {
      loadingText = lastEvent.title;
    }
    displayMessages.push({
      role: "system_status",
      content: loadingText
    });
  }

  const signature = JSON.stringify("""

content = content.replace(old_logic, new_logic)

old_render = """    const inner = role === "assistant" 
      ? renderAssistantBlocks(messageBlocks(msg)) 
      : escapeHtml(String(msg.content || ""));

    if (!node) {
      node = document.createElement("div");
      els.messageList.appendChild(node);
    }

    const existingWidgets = new Map();"""

new_render = """    let inner = "";
    if (role === "assistant") {
      inner = renderAssistantBlocks(messageBlocks(msg));
    } else if (role === "system_status") {
      inner = `
        <div style="display: flex; align-items: center; gap: 8px; color: var(--muted); font-size: 13px;">
          <style>@keyframes spin { 100% { transform: rotate(360deg); } }</style>
          <svg viewBox="0 0 50 50" style="width: 14px; height: 14px; animation: spin 1s linear infinite;">
            <circle cx="25" cy="25" r="20" fill="none" stroke="currentColor" stroke-width="6" stroke-dasharray="31.4 31.4" stroke-linecap="round"></circle>
          </svg>
          <span>${escapeHtml(msg.content)}...</span>
        </div>
      `;
    } else {
      inner = escapeHtml(String(msg.content || ""));
    }

    if (!node) {
      node = document.createElement("div");
      els.messageList.appendChild(node);
    }

    if (role === "system_status") {
      node.className = `message system-status-message`;
      node.style.background = "transparent";
      node.style.border = "none";
      node.style.padding = "4px 12px";
      node.style.boxShadow = "none";
    } else {
      node.className = `message ${role}`;
      // Clear inline styles if any
      node.style.background = "";
      node.style.border = "";
      node.style.padding = "";
      node.style.boxShadow = "";
    }

    const existingWidgets = new Map();"""

content = content.replace(old_render, new_render)

# Remove the old node.className assignment since we do it inside the if block now
old_classname = """    node.querySelectorAll("details.chat-think-details").forEach(d => {
      existingDetails.push(d.open);
    });
    
    node.className = `message ${role}`;
    node.dataset.sig = sig;
    node.innerHTML = inner;"""

new_classname = """    node.querySelectorAll("details.chat-think-details").forEach(d => {
      existingDetails.push(d.open);
    });
    
    node.dataset.sig = sig;
    node.innerHTML = inner;"""

content = content.replace(old_classname, new_classname)

with open("/Users/zhaoyu/Documents/agent-framework/app/web_static/app.js", "w") as f:
    f.write(content)

print("Applied loading indicator patch")
