const els = {
  connectionBadge: document.getElementById("connectionBadge"),
  statusBadge: document.getElementById("statusBadge"),
  nodeBadge: document.getElementById("nodeBadge"),
  stopBtn: document.getElementById("stopBtn"),
  clearBtn: document.getElementById("clearBtn"),
  chatForm: document.getElementById("chatForm"),
  messageInput: document.getElementById("messageInput"),
  sendBtn: document.getElementById("sendBtn"),
  messageList: document.getElementById("messageList"),
  modelOutput: document.getElementById("modelOutput"),
  eventList: document.getElementById("eventList"),
  todoList: document.getElementById("todoList"),
  routeList: document.getElementById("routeList"),
  complexityValue: document.getElementById("complexityValue"),
  currentNodeValue: document.getElementById("currentNodeValue"),
};

const SESSION_STORAGE_KEY = "agent_session_id";

function getSessionId() {
  let id = localStorage.getItem(SESSION_STORAGE_KEY);
  if (!id) {
    id = crypto.randomUUID ? crypto.randomUUID() : ([1e7]+-1e3+-4e3+-8e3+-1e11).replace(/[018]/g, c =>
      (c ^ crypto.getRandomValues(new Uint8Array(1))[0] & 15 >> c / 4).toString(16)
    );
    localStorage.setItem(SESSION_STORAGE_KEY, id);
  }
  return id;
}

const sessionId = getSessionId();

const expandedEvents = new Set();
const ROUTE_GROUPS = [
  ["START", "orchestrator", "agent", "orchestrator", "evaluate", "END"],
  ["agent", "tools", "orchestrator"],
  ["evaluate", "orchestrator"],
];
let mermaidModulePromise;
let routeRenderVersion = 0;

if (window.marked) {
  const renderer = new marked.Renderer();
  renderer.code = (tokenOrCode, infostring) => {
    const text = typeof tokenOrCode === "object" && tokenOrCode !== null ? tokenOrCode.text : tokenOrCode;
    const lang = typeof tokenOrCode === "object" && tokenOrCode !== null ? tokenOrCode.lang : infostring;
    const language = String(lang || "").split(/\s+/)[0] || "text";
    const canHighlight = window.hljs && language !== "text" && hljs.getLanguage(language);
    const highlighted = canHighlight
      ? hljs.highlight(String(text ?? ""), { language }).value
      : escapeHtml(text);
    return `
      <figure class="code-block">
        <figcaption>${escapeHtml(language)}</figcaption>
        <pre><code class="hljs language-${escapeHtml(language)}">${highlighted}</code></pre>
      </figure>
    `;
  };
  marked.setOptions({
    breaks: true,
    gfm: true,
    renderer,
  });
  if (window.markedKatex) {
    marked.use(window.markedKatex({
      throwOnError: false
    }));
  }
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function statusLabel(status) {
  const labels = {
    idle: "空闲",
    running: "运行中",
    cancelled: "已停止",
    error: "错误",
    pending: "待处理",
    in_progress: "进行中",
    completed: "完成",
    blocked: "阻塞",
    success: "成功",
    llm_token: "模型输出",
    llm_start: "模型开始",
    llm_end: "模型结束",
    node_update: "节点",
    todo_update: "Todo",
    tool_start: "Tool 开始",
    tool_end: "Tool 完成",
    tool_error: "Tool 失败",
    tool_message: "Tool 结果",
    run_start: "开始",
    run_complete: "完成",
    run_cancelled: "停止",
    run_error: "失败",
    clear: "清空",
  };
  return labels[status] || status || "-";
}

function setBadge(el, text, className) {
  el.className = `badge ${className || "neutral"}`;
  el.textContent = text;
}

function renderAssistantMarkdown(content) {
  if (!window.marked || !window.DOMPurify) {
    return escapeHtml(content);
  }
  return DOMPurify.sanitize(marked.parse(content), {
    USE_PROFILES: { html: true, mathMl: true },
    ADD_ATTR: ["class", "style", "xmlns"]
  });
}

function renderMessages(messages) {
  if (!messages.length) {
    els.messageList.innerHTML = `<div class="empty">暂无对话</div>`;
    return;
  }

  els.messageList.innerHTML = messages
    .map((message) => {
      const role = escapeHtml(message.role || "assistant");
      const rawContent = String(message.content || "");
      const content = role === "assistant"
        ? renderAssistantMarkdown(rawContent)
        : escapeHtml(rawContent);
      return `<div class="message ${role}">${content}</div>`;
    })
    .join("");
  els.messageList.scrollTop = els.messageList.scrollHeight;
}

function renderEvents(events) {
  if (!events.length) {
    els.eventList.innerHTML = `<div class="empty">暂无事件</div>`;
    return;
  }

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
      return `
        <div class="event-row ${expanded ? "expanded" : ""}" data-event-id="${id}">
          <div class="event-summary">
            <span class="event-main">
              <span class="event-title">${title}</span>
              <span class="event-time">${time}${updatedAt ? ` · ${updatedAt}` : ""}</span>
            </span>
            <span class="badge ${className}">${statusLabel(type)}</span>
            <button class="event-detail-button" type="button" data-event-id="${id}">${expanded ? "收起" : "详情"}</button>
          </div>
          <div class="event-detail ${expanded ? "" : "hidden"}">${renderEventDetail(event)}</div>
        </div>
      `;
    })
    .join("");
}

function renderEventDetail(event) {
  const details = event.details && Object.keys(event.details).length ? event.details : event;
  const type = event.type || "";

  if (type === "llm_token" || type === "llm_end") {
    return `
      <div class="detail-block">
        <div class="detail-label">输出内容</div>
        <pre class="detail-pre">${escapeHtml(details.content || "")}</pre>
      </div>
    `;
  }

  if (type.startsWith("tool_")) {
    return `<div class="detail-kv">
      <div class="detail-kv-row"><span>Tool</span><strong>${escapeHtml(details.tool || "-")}</strong></div>
      <div class="detail-kv-row"><span>状态</span><strong>${escapeHtml(details.status || "-")}</strong></div>
      <div class="detail-kv-row detail-kv-row-block"><span>调用入参</span><pre class="detail-pre">${escapeHtml(details.input || "")}</pre></div>
      <div class="detail-kv-row detail-kv-row-block"><span>${details.error ? "错误" : "输出结果"}</span><pre class="detail-pre">${escapeHtml(details.output || details.error || "")}</pre></div>
    </div>`;
  }

  if (type === "todo_update") {
    return `
      <div class="detail-grid">
        <div><span class="detail-label">复杂度</span><strong>${escapeHtml(details.task_complexity || "unknown")}</strong></div>
        <div><span class="detail-label">变化</span><strong>${escapeHtml(formatTodoChanges(details.changed || {}))}</strong></div>
      </div>
      <div class="detail-block">
        <div class="detail-label">更新后 Todo</div>
        ${renderTodoDetailList(details.current_todo_list || [])}
      </div>
      <div class="detail-block">
        <div class="detail-label">更新前 Todo JSON</div>
        <pre class="detail-pre">${escapeHtml(JSON.stringify(details.previous_todo_list || [], null, 2))}</pre>
      </div>
    `;
  }

  if (type === "node_update") {
    const update = details.update || {};
    const messages = update.messages || [];
    const toolCalls = messages.flatMap((message) => message.tool_calls || []);
    const stateFields = Object.keys(update).filter((key) => key !== "messages");
    return `
      <div class="detail-grid">
        <div><span class="detail-label">节点</span><strong>${escapeHtml(details.node || event.node || "-")}</strong></div>
        <div><span class="detail-label">更新字段</span><strong>${escapeHtml(stateFields.join(", ") || "messages")}</strong></div>
      </div>
      <div class="detail-block">
        <div class="detail-label">消息摘要</div>
        ${renderMessageSummary(messages)}
      </div>
      ${toolCalls.length ? `
        <div class="detail-block">
          <div class="detail-label">Tool calls</div>
          <pre class="detail-pre compact">${escapeHtml(JSON.stringify(toolCalls, null, 2))}</pre>
        </div>
      ` : ""}
      ${stateFields.length ? `
        <div class="detail-block">
          <div class="detail-label">状态字段</div>
          <pre class="detail-pre compact">${escapeHtml(JSON.stringify(pickFields(update, stateFields), null, 2))}</pre>
        </div>
      ` : ""}
    `;
  }

  return `
    <div class="detail-block">
      <div class="detail-label">事件详情</div>
      <pre class="detail-pre">${escapeHtml(JSON.stringify(details, null, 2))}</pre>
    </div>
  `;
}

function formatTodoChanges(changed) {
  const names = [];
  if (changed.todo_list) names.push("todo");
  if (changed.task_complexity) names.push("复杂度");
  if (changed.orchestrator_next) names.push("路由");
  return names.length ? names.join(", ") : "无";
}

function pickFields(source, fields) {
  return fields.reduce((result, field) => {
    result[field] = source[field];
    return result;
  }, {});
}

function renderMessageSummary(messages) {
  if (!messages.length) return `<div class="empty">无消息更新</div>`;
  return messages
    .map((message) => {
      const role = escapeHtml(message.role || "assistant");
      const content = String(message.content || "").replace(/\s+/g, " ").trim();
      const preview = content.length > 180 ? `${content.slice(0, 180)}...` : content;
      const toolCallCount = (message.tool_calls || []).length;
      return `
        <div class="message-summary-row">
          <span class="badge neutral">${role}</span>
          <span>${escapeHtml(preview || "(空内容)")}</span>
          ${toolCallCount ? `<small>${toolCallCount} tool call(s)</small>` : ""}
        </div>
      `;
    })
    .join("");
}

function renderTodoDetailList(items) {
  const flat = flattenTodos(items);
  if (!flat.length) return `<div class="empty">暂无 todo</div>`;
  return flat
    .map((item) => {
      const status = escapeHtml(item.status || "pending");
      return `
        <div class="todo-detail-row" data-depth="${Math.min(item.depth || 0, 2)}">
          <span>${escapeHtml(item.id || "-")} ${escapeHtml(item.title || "")}</span>
          <span class="badge ${status}">${statusLabel(status)}</span>
          ${item.note ? `<small>${escapeHtml(item.note)}</small>` : ""}
        </div>
      `;
    })
    .join("");
}

function flattenTodos(items, depth = 0) {
  return (items || []).flatMap((item) => [
    { ...item, depth },
    ...flattenTodos(item.children || [], depth + 1),
  ]);
}

function renderTodos(items) {
  const flat = flattenTodos(items);
  if (!flat.length) {
    els.todoList.className = "todo-list empty";
    els.todoList.textContent = "暂无 todo";
    return;
  }

  els.todoList.className = "todo-list";
  els.todoList.innerHTML = flat
    .map((item) => {
      const status = escapeHtml(item.status || "pending");
      return `
        <div class="todo-row" data-depth="${Math.min(item.depth || 0, 2)}">
          <div class="todo-meta">
            <span class="todo-title">${escapeHtml(item.id || "-")} ${escapeHtml(item.title || "")}</span>
            <span class="badge ${status}">${statusLabel(status)}</span>
          </div>
          ${item.note ? `<div class="todo-note">${escapeHtml(item.note)}</div>` : ""}
        </div>
      `;
    })
    .join("");
}

function routeLabel(route) {
  const labels = {
    START: "START",
    orchestrator: "Orchestrator",
    agent: "Agent",
    tools: "Tools",
    evaluate: "Evaluator",
    END: "END",
  };
  return labels[route] || route;
}

function collectVisitedRoutes(state) {
  const visited = new Set();
  for (const event of state.events || []) {
    if (event.type === "run_start") {
      visited.add("START");
      visited.add("orchestrator");
    }
    if (event.type === "node_update") {
      const node = event.node || event.details?.node;
      if (node) visited.add(node);
    }
    if (event.type === "tool_start" || event.type === "tool_end" || event.type === "tool_error" || event.type === "tool_message") {
      visited.add("tools");
    }
    if (event.type === "run_complete") {
      visited.add("END");
    }
  }
  if (state.current_node) visited.add(state.current_node);
  return visited;
}

function collectRouteSequence(state) {
  const sequence = [];
  const events = state.events || [];
  const lastRunStartIndex = events.map((event) => event.type).lastIndexOf("run_start");
  const routeEvents = lastRunStartIndex >= 0 ? events.slice(lastRunStartIndex) : events;
  for (const event of routeEvents) {
    if (event.type === "run_start") {
      sequence.push("START", "orchestrator");
    }
    if (event.type === "node_update") {
      const node = event.node || event.details?.node;
      if (node) sequence.push(node);
    }
    if (event.type === "tool_start" || event.type === "tool_end" || event.type === "tool_error" || event.type === "tool_message") {
      sequence.push("tools");
    }
    if (event.type === "run_complete") {
      sequence.push("END");
    }
  }

  const deduped = [];
  for (const route of sequence) {
    if (deduped[deduped.length - 1] !== route) {
      deduped.push(route);
    }
  }
  return deduped;
}

function collectRouteEdgeLabels(state) {
  const sequence = collectRouteSequence(state);
  const labels = new Map();
  let step = 1;

  for (let index = 1; index < sequence.length; index += 1) {
    const from = sequence[index - 1];
    const to = sequence[index];
    if (from === to) continue;
    const key = `${from}->${to}`;
    if (!labels.has(key)) {
      labels.set(key, []);
    }
    labels.get(key).push(step);
    step += 1;
  }

  return labels;
}

function routeClass(route, active, visited) {
  if (active === route) return "active";
  if (visited.has(route)) return "visited";
  return "idle";
}

function mermaidNodeClass(route, active, visited) {
  return routeClass(route, active, visited);
}

function buildRouteMermaidDefinition(active, visited, edgeLabels) {
  const nodeClasses = {
    S: mermaidNodeClass("START", active, visited),
    O: mermaidNodeClass("orchestrator", active, visited),
    A: mermaidNodeClass("agent", active, visited),
    E: mermaidNodeClass("evaluate", active, visited),
    X: mermaidNodeClass("END", active, visited),
    T: mermaidNodeClass("tools", active, visited),
  };

  const classLines = Object.entries(nodeClasses)
    .map(([node, className]) => `class ${node} ${className};`)
    .join("\n");
  const edges = [
    ["START->orchestrator", "S", "O", "solid"],
    ["orchestrator->agent", "O", "A", "solid"],
    ["agent->orchestrator", "A", "O", "solid"],
    ["orchestrator->evaluate", "O", "E", "solid"],
    ["evaluate->END", "E", "X", "solid"],
    ["agent->tools", "A", "T", "dotted"],
    ["tools->orchestrator", "T", "O", "dotted"],
    ["evaluate->orchestrator", "E", "O", "dotted"],
  ];
  const nodeSyntax = {
    S: 'S(["START"])',
    O: 'O["Orchestrator"]',
    A: 'A["Agent"]',
    E: 'E["Evaluator"]',
    X: 'X(["END"])',
    T: 'T["Tools"]',
  };
  const edgeLines = edges.map(([key, from, to, style]) => {
    const label = edgeLabels.get(key)?.join(", ");
    const fromNode = nodeSyntax[from];
    const toNode = nodeSyntax[to];
    if (!label) {
      return `  ${fromNode} ${style === "dotted" ? "-.->" : "-->"} ${toNode}`;
    }
    if (style === "dotted") {
      return `  ${fromNode} -. ${label} .-> ${toNode}`;
    }
    return `  ${fromNode} -->|${label}| ${toNode}`;
  }).join("\n");
  const linkStyles = edges
    .map(([key], index) => edgeLabels.has(key) ? `  linkStyle ${index} stroke:#2563eb,stroke-width:3px;` : "")
    .filter(Boolean)
    .join("\n");

  return `
flowchart TD
${edgeLines}

  classDef idle fill:#f3f6fa,stroke:#d9e1ec,color:#667085,stroke-width:1px;
  classDef visited fill:#eaf1ff,stroke:#bdd2fb,color:#2563eb,stroke-width:1.5px;
  classDef active fill:#e8f7ee,stroke:#15803d,color:#15803d,stroke-width:3px;
  ${classLines}
${linkStyles}
`;
}

function loadMermaid() {
  if (!mermaidModulePromise) {
    mermaidModulePromise = import("https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs")
      .then((module) => {
        module.default.initialize({
          startOnLoad: false,
          securityLevel: "strict",
          theme: "base",
          flowchart: {
            curve: "basis",
            htmlLabels: false,
            nodeSpacing: 18,
            rankSpacing: 22,
          },
          themeVariables: {
            fontFamily: "Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif",
            primaryColor: "#f3f6fa",
            primaryBorderColor: "#d9e1ec",
            primaryTextColor: "#162033",
            lineColor: "#98a2b3",
          },
        });
        return module.default;
      });
  }
  return mermaidModulePromise;
}

async function renderMermaidRouteDiagram(definition, version) {
  try {
    const mermaid = await loadMermaid();
    if (version !== routeRenderVersion) return;
    const { svg } = await mermaid.render("routeGraph", definition);
    if (version !== routeRenderVersion) return;
    const diagram = els.routeList.querySelector(".route-diagram");
    if (diagram) {
      diagram.innerHTML = svg;
      const renderedSvg = diagram.querySelector("svg");
      if (renderedSvg) {
        renderedSvg.removeAttribute("height");
        renderedSvg.removeAttribute("width");
        renderedSvg.style.maxWidth = "100%";
        renderedSvg.style.maxHeight = "100%";
        renderedSvg.style.width = "100%";
        renderedSvg.style.height = "100%";
      }
      diagram.classList.remove("loading");
    }
  } catch (error) {
    const notice = els.routeList.querySelector(".route-library-error");
    if (notice) {
      notice.textContent = `Mermaid 加载失败：${error.message}`;
      notice.classList.remove("hidden");
    }
  }
}

function renderRoutes(state) {
  const active = state.current_node || "";
  const visited = collectVisitedRoutes(state);
  const edgeLabels = collectRouteEdgeLabels(state);
  const mermaidDefinition = buildRouteMermaidDefinition(active, visited, edgeLabels);
  const renderVersion = ++routeRenderVersion;

  els.routeList.innerHTML = `
    <div class="route-diagram loading">正在加载 Mermaid 流程图...</div>
    <div class="route-library-error hidden"></div>
  `;
  renderMermaidRouteDiagram(mermaidDefinition, renderVersion);
}

function renderState(state) {
  const status = state.status || "idle";
  setBadge(els.statusBadge, statusLabel(status), status);
  const node = state.current_node || "-";
  setBadge(els.nodeBadge, node === "-" ? "无节点" : node, node === "-" ? "neutral" : "running");
  els.currentNodeValue.textContent = node;
  els.complexityValue.textContent = state.task_complexity || "unknown";
  els.stopBtn.disabled = status !== "running";
  els.sendBtn.disabled = status === "running";
  els.messageInput.disabled = status === "running";
  els.modelOutput.textContent = state.model_output || "等待模型输出...";

  renderMessages(state.messages || []);
  renderEvents(state.events || []);
  renderTodos(state.todo_list || []);
  renderRoutes(state);
}

function sessionHeaders() {
  return {
    "Content-Type": "application/json",
    "X-Session-Id": sessionId,
  };
}

async function loadState() {
  const response = await fetch(`/api/state?session_id=${encodeURIComponent(sessionId)}`, {
    headers: sessionHeaders(),
  });
  const state = await response.json();
  if (state.session_id) {
    localStorage.setItem(SESSION_STORAGE_KEY, state.session_id);
  }
  renderState(state);
}

function connectWs() {
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${protocol}://${window.location.host}/ws?session_id=${encodeURIComponent(sessionId)}`);

  ws.addEventListener("open", () => {
    setBadge(els.connectionBadge, "已连接", "success");
  });

  ws.addEventListener("message", (message) => {
    const payload = JSON.parse(message.data);
    renderState(payload.state);
  });

  ws.addEventListener("close", () => {
    setBadge(els.connectionBadge, "已断开", "error");
    setTimeout(connectWs, 1200);
  });
}

els.chatForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = els.messageInput.value.trim();
  if (!message) return;

  const response = await fetch(`/api/chat?session_id=${encodeURIComponent(sessionId)}`, {
    method: "POST",
    headers: sessionHeaders(),
    body: JSON.stringify({ message }),
  });

  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    alert(payload.detail || "发送失败");
    return;
  }

  els.messageInput.value = "";
  renderRoutes({ current_node: "", events: [] });
});

els.messageInput.addEventListener("keydown", (event) => {
  if (event.key !== "Enter" || event.shiftKey || event.isComposing) {
    return;
  }
  event.preventDefault();
  if (!els.sendBtn.disabled) {
    els.chatForm.requestSubmit();
  }
});

els.stopBtn.addEventListener("click", async () => {
  await fetch(`/api/stop?session_id=${encodeURIComponent(sessionId)}`, {
    method: "POST",
    headers: sessionHeaders(),
  });
});

els.clearBtn.addEventListener("click", async () => {
  await fetch(`/api/clear?session_id=${encodeURIComponent(sessionId)}`, {
    method: "POST",
    headers: sessionHeaders(),
  });
  await loadState();
});

els.eventList.addEventListener("click", (event) => {
  const button = event.target.closest(".event-detail-button");
  if (!button) return;
  const eventId = button.dataset.eventId;
  if (!eventId) return;
  if (expandedEvents.has(eventId)) {
    expandedEvents.delete(eventId);
  } else {
    expandedEvents.add(eventId);
  }
  loadState();
});

loadState();
connectWs();
