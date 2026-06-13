with open("/Users/zhaoyu/Documents/agent-framework/app/web_static/app.js", "r") as f:
    content = f.read()

import re

# Patch renderEvents
events_start = re.search(r'function renderEvents\(events\) \{', content)
if events_start:
    old_events = content[events_start.start():content.find('function flattenTodos(items)', events_start.start())]
    new_events = """
let lastEventsSignature = null;
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


# Patch renderApprovals
approvals_start = re.search(r'function renderApprovals\(approvals\) \{', content)
if approvals_start:
    old_approvals = content[approvals_start.start():content.find('function initDraggablePanel()', approvals_start.start())]
    new_approvals = """
let lastApprovalsSignature = null;
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
        <button type="button" class="button primary approve-btn" data-id="${escapeHtml(app.id)}">同意 (Approve)</button>
        <button type="button" class="button danger reject-btn" data-id="${escapeHtml(app.id)}">拒绝 (Reject)</button>
      </div>
    </div>
  `).join("");
}
"""
    content = content.replace(old_approvals, new_approvals)


# Patch renderTodos
todos_start = re.search(r'function renderTodos\(items\) \{', content)
if todos_start:
    old_todos = content[todos_start.start():content.find('function renderApprovals', todos_start.start())]
    new_todos = """
let lastTodosSignature = null;
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


content = content.replace("app.js?v=9", "app.js?v=10")
content = content.replace("styles.css?v=9", "styles.css?v=10")

with open("/Users/zhaoyu/Documents/agent-framework/app/web_static/app.js", "w") as f:
    f.write(content)
print("Patched rendering signatures!")
