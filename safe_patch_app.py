import re

with open("/Users/zhaoyu/Documents/agent-framework/app/web_static/app.js", "r") as f:
    content = f.read()

# 1. Add parseMessageBlocksJS before renderMessages
if "function parseMessageBlocksJS" not in content:
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
    content = content.replace("let lastMessagesSignature = null;", parse_msg_code + "\nlet lastMessagesSignature = null;")

# 2. Replace renderMessages with DOM diffing
render_msgs_start = re.search(r'function renderMessages\(messages\) \{', content)
if render_msgs_start:
    end_match = content.find('function hydrateWidgets(root) {', render_msgs_start.start())
    old_render_msgs = content[render_msgs_start.start():end_match]
    
    new_render_msgs = """function renderMessages(messages, status, model_output) {
  const isAtBottom = isFirstRender || (els.messageList.scrollHeight - els.messageList.scrollTop - els.messageList.clientHeight <= 50);

  const displayMessages = [...messages];
  if (status === "running" && model_output) {
    const parsedBlocks = parseMessageBlocksJS(model_output);
    if (parsedBlocks) {
      displayMessages.push({ role: "assistant", content: model_output, blocks: parsedBlocks });
    } else {
      displayMessages.push({ role: "assistant", content: model_output });
    }
  }

  if (!displayMessages.length) {
    els.messageList.innerHTML = `<div class="empty">暂无对话</div>`;
    isFirstRender = false;
    return;
  }

  const emptyEl = els.messageList.querySelector('.empty');
  if (emptyEl) {
    els.messageList.innerHTML = '';
  }

  while (els.messageList.children.length > displayMessages.length) {
    els.messageList.removeChild(els.messageList.lastChild);
  }

  for (let i = 0; i < displayMessages.length; i++) {
    const msg = displayMessages[i];
    let child = els.messageList.children[i];
    
    const role = escapeHtml(msg.role || "assistant");
    const sig = JSON.stringify({ role: msg.role, blocks: msg.blocks || null, content: msg.content || "" });
    const className = `message ${role}`;

    if (!child) {
      child = document.createElement('div');
      child.className = className;
      child.dataset.sig = sig;
      const inner = (role === "assistant") ? renderAssistantBlocks(messageBlocks(msg)) : escapeHtml(String(msg.content || ""));
      child.innerHTML = inner;
      els.messageList.appendChild(child);
      hydrateWidgets(child);
    } else {
      if (child.className !== className) {
        child.className = className;
      }
      if (child.dataset.sig !== sig) {
        child.dataset.sig = sig;
        const inner = (role === "assistant") ? renderAssistantBlocks(messageBlocks(msg)) : escapeHtml(String(msg.content || ""));
        child.innerHTML = inner;
        hydrateWidgets(child);
      }
    }
  }
  
  if (isAtBottom) {
    els.messageList.scrollTop = els.messageList.scrollHeight;
  }
  
  els.messageList.querySelectorAll('.chat-think-details[open] .chat-think-content').forEach(el => {
    el.scrollTop = el.scrollHeight;
  });
  
  isFirstRender = false;
}
"""
    content = content.replace(old_render_msgs, new_render_msgs)

# 3. Patch renderState (add RAF throttling, remove modelOutput, pass status/model_output to renderMessages)
render_state_start = re.search(r'function renderState\(state\) \{', content)
if render_state_start:
    end_match = content.find('function sessionHeaders() {', render_state_start.start())
    old_render_state = content[render_state_start.start():end_match]
    
    new_render_state = """let renderStateRafId = null;

function renderState(state) {
  currentState = { ...currentState, ...(state || {}) };
  
  if (renderStateRafId) return;
  
  renderStateRafId = requestAnimationFrame(() => {
    renderStateRafId = null;
    const state = currentState;
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
  });
}
"""
    content = content.replace(old_render_state, new_render_state)

# 4. Patch renderEvents
events_start = re.search(r'function renderEvents\(events\) \{', content)
if events_start:
    end_match = content.find('function renderApprovals(approvals)', events_start.start())
    if end_match == -1: end_match = content.find('function flattenTodos', events_start.start()) # fallback
    old_events = content[events_start.start():end_match]
    new_events = """let lastEventsSignature = null;
function renderEvents(events) {
  const currentSignature = JSON.stringify(events);
  if (currentSignature === lastEventsSignature) return;
  lastEventsSignature = currentSignature;

  if (!events.length) {
    els.eventList.innerHTML = `<div class="empty">暂无事件</div>`;
    return;
  }

  const stepMap = calculateEventStepNumbers(events);

  els.eventList.innerHTML = events
    .slice()
    .reverse()
    .map((event) => {
      const rawId = event.id || `${event.type}-${event.time}`;
      const id = escapeHtml(rawId);
      const expanded = expandedEvents.has(rawId);
      const type = escapeHtml(event.type || "event");
      const title = escapeHtml(event.title || event.type || "事件");
      const time = escapeHtml(event.time || "");
      const updatedAt = event.updated_at ? `更新 ${escapeHtml(event.updated_at)}` : "";
      const className = event.type?.includes("error") ? "error" : event.type?.includes("complete") || event.type?.includes("end") ? "success" : "neutral";
      
      const stepNum = stepMap.get(rawId);
      const stepIndicator = stepNum ? `<span class="event-step-number">${stepNum}</span>` : "";

      return `
        <div class="event-row ${expanded ? "expanded" : ""}" data-event-id="${id}">
          <div class="event-summary">
            <span class="event-main">
              <span class="event-title">${stepIndicator}${title}</span>
              <span class="event-time">${time}${updatedAt ? ` · ${updatedAt}` : ""}</span>
            </span>
            <span class="badge ${className}">${statusLabel(type)}</span>
            <button class="event-detail-button" type="button" data-event-id="${id}">${expanded ? "收起" : "详情"}</button>
          </div>
          <div class="event-detail">${expanded && event.details ? escapeHtml(JSON.stringify(event.details, null, 2)) : ""}</div>
        </div>
      `;
    })
    .join("");
}
"""
    content = content.replace(old_events, new_events)

# 5. Patch renderApprovals
approvals_start = re.search(r'function renderApprovals\(approvals\) \{', content)
if approvals_start:
    end_match = content.find('function renderTodos(items)', approvals_start.start())
    if end_match == -1: end_match = content.find('function initDraggablePanel()', approvals_start.start())
    old_approvals = content[approvals_start.start():end_match]
    new_approvals = """let lastApprovalsSignature = null;
function renderApprovals(approvals) {
  if (!els.approvalList) return;
  const currentSignature = JSON.stringify(approvals);
  if (currentSignature === lastApprovalsSignature) return;
  lastApprovalsSignature = currentSignature;

  if (!approvals || !approvals.length) {
    els.approvalList.className = "approval-list empty";
    els.approvalList.textContent = "暂无审批";
    return;
  }
  els.approvalList.className = "approval-list";
  els.approvalList.innerHTML = approvals.map(app => `
    <div class="approval-card">
      <div class="approval-header">
        <span class="approval-title">需要用户审批</span>
        <span class="badge warning">${escapeHtml(app.status || "")}</span>
      </div>
      <div class="approval-body">
        <div><strong>请求操作：</strong>${escapeHtml(app.action || "")}</div>
        <div><strong>操作目标：</strong>${escapeHtml(app.target_uri || app.target_path || app.host_path || "")}</div>
        <div><strong>原因说明：</strong>${escapeHtml(app.reason || "")}</div>
      </div>
      <div class="approval-actions">
        <button type="button" class="button primary approve-btn" data-approval-id="${escapeHtml(app.id)}">同意 (Approve)</button>
        <button type="button" class="button danger reject-btn" data-approval-id="${escapeHtml(app.id)}">拒绝 (Reject)</button>
      </div>
    </div>
  `).join("");
}
"""
    content = content.replace(old_approvals, new_approvals)

# 6. Patch renderTodos
todos_start = re.search(r'function renderTodos\(items\) \{', content)
if todos_start:
    end_match = content.find('function initDraggablePanel()', todos_start.start())
    if end_match == -1: end_match = content.find('function activeModelPayload', todos_start.start())
    old_todos = content[todos_start.start():end_match]
    new_todos = """let lastTodosSignature = null;
function renderTodos(items) {
  const currentSignature = JSON.stringify(items);
  if (currentSignature === lastTodosSignature) return;
  lastTodosSignature = currentSignature;

  const flat = flattenTodos(items);
  if (!flat.length) {
    els.todoList.className = "todo-list empty";
    els.todoList.textContent = "暂无 todo";
    return;
  }

  els.todoList.className = "todo-list";
  els.todoList.innerHTML = flat
    .map((item) => {
      let icon = "⚪";
      let textClass = "";
      if (item.status === "done") {
        icon = "✅";
        textClass = "done";
      } else if (item.status === "in_progress") {
        icon = "🔄";
      }
      return `
        <div class="todo-item" style="padding-left: ${item.depth * 1.5}rem;">
          <span class="todo-icon">${icon}</span>
          <span class="todo-text ${textClass}">${escapeHtml(item.text)}</span>
        </div>
      `;
    })
    .join("");
}
"""
    content = content.replace(old_todos, new_todos)

with open("/Users/zhaoyu/Documents/agent-framework/app/web_static/app.js", "w") as f:
    f.write(content)

print("Safe patch applied successfully!")
