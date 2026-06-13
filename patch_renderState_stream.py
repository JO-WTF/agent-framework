import re

with open("/Users/zhaoyu/Documents/agent-framework/app/web_static/app.js", "r") as f:
    content = f.read()

# 1. Update renderState definition and logic
old_renderState = """function renderState(state) {
  currentState = { ...currentState, ...(state || {}) };
  state = currentState;
  const status = state.status || "idle";
  setBadge(els.statusBadge, statusLabel(status), status);
  const node = state.current_node || "-";
  setBadge(els.nodeBadge, node === "-" ? "无节点" : node, node === "-" ? "neutral" : "running");
  els.currentNodeValue.textContent = node;
  els.complexityValue.textContent = state.task_complexity || "unknown";
  els.stopBtn.disabled = status !== "running";
  els.sendBtn.disabled = status === "running" || status === "awaiting_approval";
  els.messageInput.disabled = status === "running" || status === "awaiting_approval";
  if (els.saveModelConfigBtn) {
    els.saveModelConfigBtn.disabled = status === "running" || status === "awaiting_approval";
  }


  renderMessages(state.messages || [], status, state.model_output);
  renderEvents(state.events || []);
  renderApprovals(state.world_state?.pending_approvals || []);
  renderTodos(state.todo_list || []);
  renderRoutes(state);
}"""

new_renderState = """function renderState(state, isStream = false) {
  currentState = { ...currentState, ...(state || {}) };
  state = currentState;
  const status = state.status || "idle";
  
  if (!isStream) {
    setBadge(els.statusBadge, statusLabel(status), status);
    const node = state.current_node || "-";
    setBadge(els.nodeBadge, node === "-" ? "无节点" : node, node === "-" ? "neutral" : "running");
    els.currentNodeValue.textContent = node;
    els.complexityValue.textContent = state.task_complexity || "unknown";
    els.stopBtn.disabled = status !== "running";
    els.sendBtn.disabled = status === "running" || status === "awaiting_approval";
    els.messageInput.disabled = status === "running" || status === "awaiting_approval";
    if (els.saveModelConfigBtn) {
      els.saveModelConfigBtn.disabled = status === "running" || status === "awaiting_approval";
    }
  }

  renderMessages(state.messages || [], status, state.model_output);
  
  if (!isStream) {
    renderEvents(state.events || []);
    renderApprovals(state.world_state?.pending_approvals || []);
    renderTodos(state.todo_list || []);
    renderRoutes(state);
  }
}"""

content = content.replace(old_renderState, new_renderState)

# 2. Update ws payload.type === "stream" handler
old_ws = """      } else if (payload.type === "stream") {
        renderState({ model_output: (currentState.model_output || "") + (payload.content || "") });
      }"""
new_ws = """      } else if (payload.type === "stream") {
        renderState({ model_output: (currentState.model_output || "") + (payload.content || "") }, true);
      }"""

content = content.replace(old_ws, new_ws)

with open("/Users/zhaoyu/Documents/agent-framework/app/web_static/app.js", "w") as f:
    f.write(content)

print("Applied renderState stream optimization!")
