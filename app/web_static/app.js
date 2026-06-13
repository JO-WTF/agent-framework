const els = {
  connectionBadge: document.getElementById("connectionBadge"),
  statusBadge: document.getElementById("statusBadge"),
  nodeBadge: document.getElementById("nodeBadge"),
  stopBtn: document.getElementById("stopBtn"),
  newSessionBtn: document.getElementById("newSessionBtn"),
  clearBtn: document.getElementById("clearBtn"),
  modelConfigForm: document.getElementById("modelConfigForm"),
  modelProviderSelect: document.getElementById("modelProviderSelect"),
  modelPresetSelect: document.getElementById("modelPresetSelect"),
  modelNameField: document.getElementById("modelNameField"),
  modelNameInput: document.getElementById("modelNameInput"),
  modelBaseUrlInput: document.getElementById("modelBaseUrlInput"),
  modelApiKeyInput: document.getElementById("modelApiKeyInput"),
  saveModelConfigBtn: document.getElementById("saveModelConfigBtn"),
  modelConfigBadge: document.getElementById("modelConfigBadge"),
  chatForm: document.getElementById("chatForm"),
  messageInput: document.getElementById("messageInput"),
  sendBtn: document.getElementById("sendBtn"),
  messageList: document.getElementById("messageList"),
  eventList: document.getElementById("eventList"),
  todoList: document.getElementById("todoList"),
  approvalList: document.getElementById("approvalList"),
  routeList: document.getElementById("routeList"),
  progressSplit: document.getElementById("progressSplit"),
  progressResizeHandle: document.getElementById("progressResizeHandle"),
  complexityValue: document.getElementById("complexityValue"),
  currentNodeValue: document.getElementById("currentNodeValue"),
  workspace: document.querySelector(".workspace"),
  toggleRuntimeBtn: document.getElementById("toggleRuntimeBtn"),
};

const SESSION_STORAGE_KEY = "agent_session_id";
const MODEL_CONFIG_STORAGE_KEY = "agent_model_config";
const PROGRESS_SPLIT_STORAGE_KEY = "agent_progress_split_todo_px";
const PROGRESS_SPLIT_HANDLE_HEIGHT = 10;
const PROGRESS_SPLIT_MIN_TODO = 120;
const PROGRESS_SPLIT_MIN_ROUTE = 160;
const MODEL_PRESETS = {
  openai: ["gpt-4o-mini", "gpt-4o", "gpt-4.1-mini"],
  deepseek: ["deepseek-v4-flash", "deepseek-chat", "deepseek-reasoner"],
  ollama: ["qwen3", "deepseek-r1", "llama3.1"],
  llamacpp: ["qwen3.6:latest"],
  custom: ["custom-model"],
};
const PROVIDER_DEFAULT_BASE_URLS = {
  openai: "",
  deepseek: "https://api.deepseek.com/v1",
  ollama: "http://localhost:11434/v1",
  llamacpp: "http://isc.ai.huawei.com:11434/v1",
  custom: "",
};
const PROVIDER_DEFAULT_MODEL_NAMES = {
  openai: "gpt-4o-mini",
  deepseek: "deepseek-v4-flash",
  ollama: "qwen3",
  llamacpp: "qwen3.6:latest",
  custom: "custom-model",
};

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
  ["START", "orchestrator", "memory", "agent", "memory", "orchestrator", "memory", "evaluate", "END"],
  ["agent", "memory", "tools", "memory", "orchestrator"],
  ["evaluate", "orchestrator"],
];
let mermaidModulePromise;
let routeRenderVersion = 0;
let lastRenderedDefinition = "";
let mapboxAccessToken = "";
const pendingMapWidgets = [];
let currentState = {
  status: "idle",
  current_node: "",
  task_complexity: "unknown",
  todo_list: [],
  model_output: "",
  tool_runs: [],
  events: [],
  context_tags: ["general"],
  world_state: {},
  messages: [],
};


if (window.marked) {
  const renderer = new marked.Renderer();
  renderer.code = (tokenOrCode, infostring) => {
    const text = typeof tokenOrCode === "object" && tokenOrCode !== null ? tokenOrCode.text : tokenOrCode;
    const lang = typeof tokenOrCode === "object" && tokenOrCode !== null ? tokenOrCode.lang : infostring;
    const language = String(lang || "").split(/\s+/)[0] || "text";
    const canHighlight = window.hljs && language !== "text" && hljs.getLanguage(language);
    const skipHighlight = currentState && currentState.status === "running";
    const highlighted = (canHighlight && !skipHighlight)
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


function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function progressSplitBounds() {
  const split = els.progressSplit;
  if (!split) return null;
  const totalHeight = split.clientHeight;
  if (!totalHeight) return null;
  const maxTodo = Math.max(PROGRESS_SPLIT_MIN_TODO, totalHeight - PROGRESS_SPLIT_HANDLE_HEIGHT - PROGRESS_SPLIT_MIN_ROUTE);
  return { totalHeight, maxTodo };
}

function fitRouteDiagramToContainer() {
  const diagram = els.routeList?.querySelector(".route-diagram");
  const renderedSvg = diagram?.querySelector("svg");
  if (!diagram || !renderedSvg) return;

  renderedSvg.setAttribute("width", "100%");
  renderedSvg.setAttribute("height", "100%");
  renderedSvg.style.width = "100%";
  renderedSvg.style.height = "100%";
  renderedSvg.style.maxWidth = "100%";
  renderedSvg.style.maxHeight = "100%";
  renderedSvg.style.display = "block";
}

function applyProgressSplit(todoHeight, persist = false) {
  const bounds = progressSplitBounds();
  if (!bounds) return;
  const nextTodoHeight = Math.round(clamp(todoHeight, PROGRESS_SPLIT_MIN_TODO, bounds.maxTodo));
  els.progressSplit.style.gridTemplateRows = `${nextTodoHeight}px ${PROGRESS_SPLIT_HANDLE_HEIGHT}px minmax(${PROGRESS_SPLIT_MIN_ROUTE}px, 1fr)`;
  if (els.progressResizeHandle) {
    els.progressResizeHandle.setAttribute("aria-valuemin", String(PROGRESS_SPLIT_MIN_TODO));
    els.progressResizeHandle.setAttribute("aria-valuemax", String(bounds.maxTodo));
    els.progressResizeHandle.setAttribute("aria-valuenow", String(nextTodoHeight));
  }
  if (persist) {
    localStorage.setItem(PROGRESS_SPLIT_STORAGE_KEY, String(nextTodoHeight));
  }
  fitRouteDiagramToContainer();
}

function restoreProgressSplit() {
  const bounds = progressSplitBounds();
  if (!bounds) return;
  const saved = Number(localStorage.getItem(PROGRESS_SPLIT_STORAGE_KEY));
  const defaultTodoHeight = Math.round((bounds.totalHeight - PROGRESS_SPLIT_HANDLE_HEIGHT) * 0.42);
  applyProgressSplit(Number.isFinite(saved) && saved > 0 ? saved : defaultTodoHeight, false);
}

function initializeProgressSplitResizer() {
  const split = els.progressSplit;
  const handle = els.progressResizeHandle;
  if (!split || !handle) return;

  let dragStartY = 0;
  let dragStartTodoHeight = 0;

  const currentTodoHeight = () => split.querySelector(".todo-wrap")?.getBoundingClientRect().height || PROGRESS_SPLIT_MIN_TODO;

  const stopDrag = () => {
    handle.classList.remove("dragging");
    document.body.classList.remove("progress-resizing");
    window.removeEventListener("pointermove", onPointerMove);
    window.removeEventListener("pointerup", stopDrag);
  };

  function onPointerMove(event) {
    const delta = event.clientY - dragStartY;
    applyProgressSplit(dragStartTodoHeight + delta, true);
  }

  handle.addEventListener("pointerdown", (event) => {
    event.preventDefault();
    dragStartY = event.clientY;
    dragStartTodoHeight = currentTodoHeight();
    handle.classList.add("dragging");
    document.body.classList.add("progress-resizing");
    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", stopDrag);
  });

  handle.addEventListener("keydown", (event) => {
    if (!["ArrowUp", "ArrowDown", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const bounds = progressSplitBounds();
    if (!bounds) return;
    if (event.key === "Home") {
      applyProgressSplit(PROGRESS_SPLIT_MIN_TODO, true);
    } else if (event.key === "End") {
      applyProgressSplit(bounds.maxTodo, true);
    } else {
      const delta = event.key === "ArrowUp" ? -24 : 24;
      applyProgressSplit(currentTodoHeight() + delta, true);
    }
  });

  restoreProgressSplit();
  const resizeObserver = new ResizeObserver(() => {
    restoreProgressSplit();
    fitRouteDiagramToContainer();
  });
  resizeObserver.observe(split);
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
    awaiting_approval: "等待审批",
    cancelled: "已停止",
    error: "错误",
    pending: "待处理",
    in_progress: "进行中",
    completed: "完成",
    blocked: "阻塞",
    success: "成功",
    llm_run: "模型调用",
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

function parseThinkingContent(content) {
  const thinkingParts = [];
  const messageParts = [];
  const blockRe = /<think>([\s\S]*?)<\/think>/gi;
  let cursor = 0;
  let match;

  while ((match = blockRe.exec(content)) !== null) {
    messageParts.push(content.substring(cursor, match.index));
    thinkingParts.push(match[1]);
    cursor = blockRe.lastIndex;
  }

  const remainder = content.substring(cursor);
  const openMatch = /<think>([\s\S]*)$/i.exec(remainder);
  if (openMatch) {
    messageParts.push(remainder.substring(0, openMatch.index));
    thinkingParts.push(openMatch[1]);
  } else {
    messageParts.push(remainder);
  }

  return {
    think: thinkingParts.join("").trim(),
    message: messageParts.join("").trim(),
  };
}

function splitThinkingSegments(content) {
  const segments = [];
  const blockRe = /<think>([\s\S]*?)<\/think>/gi;
  let cursor = 0;
  let match;

  while ((match = blockRe.exec(content)) !== null) {
    if (match.index > cursor) {
      segments.push({ type: "content", text: content.substring(cursor, match.index) });
    }
    if (match[1]) {
      segments.push({ type: "thinking", text: match[1] });
    }
    cursor = blockRe.lastIndex;
  }

  const remainder = content.substring(cursor);
  const openMatch = /<think>([\s\S]*)$/i.exec(remainder);
  if (openMatch) {
    if (openMatch.index > 0) {
      segments.push({ type: "content", text: remainder.substring(0, openMatch.index) });
    }
    if (openMatch[1]) {
      segments.push({ type: "thinking", text: openMatch[1] });
    }
  } else if (remainder) {
    segments.push({ type: "content", text: remainder });
  }

  return segments;
}

function renderModelOutput(content) {
  if (!content) {
    return `<div class="model-output-empty">${escapeHtml("等待模型输出...")}</div>`;
  }

  const rounds = content
    .split(/\n*\[\[MODEL_OUTPUT_ROUND_BREAK\]\]\n*/g)
    .map((round) => round.trim())
    .filter(Boolean);

  if (!rounds.length) {
    return `<div class="model-output-empty">${escapeHtml("等待模型输出...")}</div>`;
  }

  return rounds.map((round, index) => {
    const segments = splitThinkingSegments(round).filter((segment) => segment.text.trim());
    const body = segments.length
      ? segments.map((segment) => {
        const isThinking = segment.type === "thinking";
        const label = isThinking ? "[思考]" : "[回复]";
        const className = isThinking ? "model-output-line thinking" : "model-output-line reply";
        return `
          <div class="${className}">
            <span class="model-output-segment-label">${label}</span>
            <span class="model-output-segment-content">${escapeHtml(segment.text.trim())}</span>
          </div>
        `;
      }).join("")
      : `
        <div class="model-output-line reply">
          <span class="model-output-segment-label">[回复]</span>
          <span class="model-output-segment-content">${escapeHtml(round)}</span>
        </div>
      `;

    return `
      <div class="model-output-round">
        <div class="model-output-round-header">第 ${index + 1} 轮</div>
        <div class="model-output-round-body">${body}</div>
      </div>
    `;
  }).join("");
}


function renderAssistantMarkdown(content) {
  if (!window.marked || !window.DOMPurify) {
    return escapeHtml(content);
  }
  
  let html = "";
  const blockRe = /<think>([\s\S]*?)<\/think>/gi;
  let cursor = 0;
  let match;

  while ((match = blockRe.exec(content)) !== null) {
    const textBefore = content.substring(cursor, match.index).trim();
    if (textBefore) {
      html += DOMPurify.sanitize(marked.parse(textBefore), {
        USE_PROFILES: { html: true, mathMl: true },
        ADD_ATTR: ["class", "style", "xmlns"]
      });
    }
    
    const thinkContent = match[1].trim();
    if (thinkContent) {
      html += `
        <details class="chat-think-details" open>
          <summary class="chat-think-summary">🧠 思考过程 (点击收起/展开)</summary>
          <div class="chat-think-content">${escapeHtml(thinkContent)}</div>
        </details>
      `;
    }
    cursor = blockRe.lastIndex;
  }

  const remainder = content.substring(cursor);
  const openMatch = /<think>([\s\S]*)$/i.exec(remainder);
  
  if (openMatch) {
    const textBefore = remainder.substring(0, openMatch.index).trim();
    if (textBefore) {
      html += DOMPurify.sanitize(marked.parse(textBefore), {
        USE_PROFILES: { html: true, mathMl: true },
        ADD_ATTR: ["class", "style", "xmlns"]
      });
    }
    const thinkContent = openMatch[1].trim();
    if (thinkContent) {
      html += `
        <details class="chat-think-details" open>
          <summary class="chat-think-summary">🧠 思考过程 (点击收起/展开)</summary>
          <div class="chat-think-content">${escapeHtml(thinkContent)}</div>
        </details>
      `;
    }
  } else if (remainder.trim()) {
    html += DOMPurify.sanitize(marked.parse(remainder.trim()), {
      USE_PROFILES: { html: true, mathMl: true },
      ADD_ATTR: ["class", "style", "xmlns"]
    });
  }

  return html || escapeHtml(content);
}

function messageBlocks(message) {
  if (Array.isArray(message.blocks) && message.blocks.length) {
    return message.blocks;
  }
  return [{ type: "text", format: "markdown", content: String(message.content || "") }];
}

function renderAssistantBlocks(blocks) {
  return blocks
    .map((block) => {
      if (block && block.type === "widget") {
        const config = { widget_type: block.widget_type, id: block.id || "", props: block.props || {} };
        return `<div class="chat-widget" data-widget="${escapeHtml(JSON.stringify(config))}"></div>`;
      }
      const text = String((block && block.content) || "");
      if (!text.trim()) return "";
      return `<div class="message-block-text">${renderAssistantMarkdown(text)}</div>`;
    })
    .join("");
}


function parseMessageBlocksJS(content) {
  if (!content) return null;
  const blocks = [];
  const regex = /(?:^[ \t]*(?:`{3,}|~{3,})[ \t]*(?:widget|json)?[ \t]*\r?\n|^[ \t]*(?:widget|json)[ \t]*\r?\n)?(\{\s*\"widget_type\"[\s\S]*?\n\})(?:\r?\n^[ \t]*(?:`{3,}|~{3,}))?/gm;
  let lastIndex = 0;
  let match;
  while ((match = regex.exec(content)) !== null) {
    const textBefore = content.substring(lastIndex, match.index);
    if (textBefore.trim()) blocks.push({ type: "text", content: textBefore.trim() });
    try {
      const payload = JSON.parse(match[1].trim());
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

let lastMessagesSignature = null;

function renderMessages(messages, status, model_output) {
  const displayMessages = [...messages];
  if (status === "running") {
    if (model_output) {
      const combinedRound = model_output.replace(/\n*\[\[MODEL_OUTPUT_ROUND_BREAK\]\]\n*/g, "\n\n").trim();
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
    
    let inner = "";
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

    const existingWidgets = new Map();
    node.querySelectorAll(".chat-widget").forEach(w => {
      if (w.dataset.hydrated) {
        existingWidgets.set(w.dataset.widget, w);
      }
    });
    
    const existingDetails = [];
    node.querySelectorAll("details.chat-think-details").forEach(d => {
      existingDetails.push(d.open);
    });
    
    node.dataset.sig = sig;
    node.innerHTML = inner;

    node.querySelectorAll("details.chat-think-details").forEach((d, index) => {
      if (index < existingDetails.length) {
        if (existingDetails[index]) {
          d.setAttribute("open", "");
        } else {
          d.removeAttribute("open");
        }
      }
    });

    node.querySelectorAll(".chat-widget").forEach(w => {
      const saved = existingWidgets.get(w.dataset.widget);
      if (saved) {
        w.parentNode.replaceChild(saved, w);
      }
    });

    hydrateWidgets(node);
  }

  // Remove excess nodes
  for (let i = displayMessages.length; i < currentNodes.length; i++) {
    if (currentNodes[i] && currentNodes[i].parentNode) {
      currentNodes[i].parentNode.removeChild(currentNodes[i]);
    }
  }


  if (isAtBottom) {
    els.messageList.scrollTop = els.messageList.scrollHeight;
  }
}

function hydrateWidgets(root) {
  root.querySelectorAll(".chat-widget").forEach((placeholder) => {
    let config;
    try {
      config = JSON.parse(placeholder.dataset.widget || "{}");
    } catch (error) {
      console.error("Failed to parse widget config", error);
      return;
    }
    const renderer = WIDGET_RENDERERS[config.widget_type] || renderUnknownWidget;
    try {
      renderer(placeholder, config.props || {}, config);
    } catch (error) {
      console.error(`Failed to render widget "${config.widget_type}"`, error);
      placeholder.classList.add("chat-widget-error");
      placeholder.textContent = `无法渲染卡片：${config.widget_type || "unknown"}`;
    }
  });
}

function createWidgetCard(placeholder, { title, icon, fullscreen = false } = {}) {
  placeholder.classList.add("widget-card");
  const card = document.createElement("div");
  card.className = "widget-card-inner";

  const header = document.createElement("div");
  header.className = "widget-card-header";
  const titleEl = document.createElement("span");
  titleEl.className = "widget-card-title";
  titleEl.innerHTML = `${icon ? `<i class="${icon}"></i> ` : ""}${escapeHtml(title || "")}`;
  header.appendChild(titleEl);

  const body = document.createElement("div");
  body.className = "widget-card-body";

  if (fullscreen) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "widget-fullscreen-btn";
    button.title = "全屏显示";
    button.setAttribute("aria-label", "全屏显示");
    button.innerHTML = `<i class="fa-solid fa-expand"></i>`;
    button.addEventListener("click", () => {
      if (document.fullscreenElement === placeholder) {
        document.exitFullscreen?.();
      } else {
        placeholder.requestFullscreen?.();
      }
    });
    header.appendChild(button);
  }

  card.appendChild(header);
  card.appendChild(body);
  placeholder.appendChild(card);
  return { card, header, body };
}

function renderMapWidget(placeholder, props, config) {
  const { body } = createWidgetCard(placeholder, { title: "地图", icon: "fa-solid fa-map-location-dot", fullscreen: true });
  const mapEl = document.createElement("div");
  mapEl.className = "widget-map";
  body.appendChild(mapEl);

  if (!window.mapboxgl) {
    mapEl.textContent = "地图库未加载";
    return;
  }

  // Handle use_stored_card
  let actualProps = { ...props };
  if (props.use_stored_card && config && config.id && currentState && Array.isArray(currentState.map_cards)) {
    const storedCard = currentState.map_cards.find(c => c.id === config.id);
    if (storedCard) {
      actualProps = { ...actualProps, ...storedCard };
    }
  }

  const token = actualProps.access_token || mapboxAccessToken;
  if (!token) {
    mapEl.className = "widget-map widget-map-pending";
    mapEl.textContent = "正在加载地图…（未配置 Mapbox Access Token）";
    pendingMapWidgets.push(() => {
      if (mapEl.isConnected && (actualProps.access_token || mapboxAccessToken)) {
        mapEl.className = "widget-map";
        mapEl.textContent = "";
        renderMapInstance(placeholder, mapEl, actualProps);
      }
    });
    return;
  }

  renderMapInstance(placeholder, mapEl, actualProps);
}

function renderMapInstance(placeholder, mapEl, props) {
  mapboxgl.accessToken = props.access_token || mapboxAccessToken;

  const points = Array.isArray(props.points) ? props.points : (Array.isArray(props.markers) ? props.markers : []);
  const lines = Array.isArray(props.lines) ? props.lines : [];
  const geojsonData = props.geojson;

  // Auto fit bounds
  const bounds = new mapboxgl.LngLatBounds();
  let hasElements = false;

  points.forEach((pt) => {
    const lat = Number(pt.lat ?? pt.latitude);
    const lng = Number(pt.lng ?? pt.longitude);
    if (!Number.isNaN(lat) && !Number.isNaN(lng)) {
      bounds.extend([lng, lat]);
      hasElements = true;
    }
  });

  lines.forEach((line) => {
    (line.coordinates || []).forEach(coord => {
      if (coord && coord.length >= 2) {
        bounds.extend([coord[0], coord[1]]); // Mapbox is [lng, lat]
        hasElements = true;
      }
    });
  });

  if (geojsonData) {
    // A simple recursive search for coordinates in GeoJSON
    const findCoords = (obj) => {
      if (!obj) return;
      if (Array.isArray(obj)) {
        if (obj.length === 2 && typeof obj[0] === 'number' && typeof obj[1] === 'number') {
          bounds.extend([obj[0], obj[1]]);
          hasElements = true;
        } else {
          obj.forEach(findCoords);
        }
      } else if (typeof obj === 'object') {
        Object.values(obj).forEach(findCoords);
      }
    };
    findCoords(geojsonData);
  }

  const mapOptions = {
    container: mapEl,
    style: props.style || "mapbox://styles/mapbox/streets-v12",
    projection: "mercator",
  };

  const center = props.center || {};
  const lat = Number(center.lat ?? center.latitude ?? 0);
  const lng = Number(center.lng ?? center.longitude ?? 0);
  const zoom = Number(props.zoom ?? 10);

  // If there are elements to fit, and the user didn't explicitly specify a zoom, fit bounds.
  // Actually, just fit bounds if we have elements, it's almost always what we want.
  if (hasElements) {
    mapOptions.bounds = bounds;
    mapOptions.fitBoundsOptions = { padding: 40, maxZoom: 15 };
  } else {
    mapOptions.center = [lng, lat];
    mapOptions.zoom = zoom;
  }

  let map;
  try {
    map = new mapboxgl.Map(mapOptions);
  } catch (error) {
    mapEl.className = "widget-map widget-map-pending";
    mapEl.textContent = `地图加载失败：${error.message}`;
    return;
  }

  map.addControl(new mapboxgl.NavigationControl({ showCompass: false }), "top-right");

  map.on('load', () => {
    // Add geojson if present
    if (geojsonData) {
      map.addSource('geojson-data', {
        type: 'geojson',
        data: geojsonData
      });
      
      // Render polygons
      map.addLayer({
        id: 'geojson-fill',
        type: 'fill',
        source: 'geojson-data',
        paint: {
          'fill-color': '#088',
          'fill-opacity': 0.4
        },
        filter: ['==', '$type', 'Polygon']
      });

      // Render lines/borders
      map.addLayer({
        id: 'geojson-line',
        type: 'line',
        source: 'geojson-data',
        paint: {
          'line-color': '#088',
          'line-width': 3
        },
        filter: ['in', '$type', 'Polygon', 'LineString']
      });
    }

    // Add lines
    lines.forEach((line, idx) => {
      const sourceId = `line-source-${idx}`;
      map.addSource(sourceId, {
        type: 'geojson',
        data: {
          type: 'Feature',
          properties: {},
          geometry: {
            type: 'LineString',
            coordinates: line.coordinates
          }
        }
      });
      map.addLayer({
        id: `line-layer-${idx}`,
        type: 'line',
        source: sourceId,
        layout: {
          'line-join': 'round',
          'line-cap': 'round'
        },
        paint: {
          'line-color': line.color || '#f97316',
          'line-width': 4
        }
      });
    });
  });

  // Add points
  points.forEach((pt) => {
    const mLat = Number(pt.lat ?? pt.latitude);
    const mLng = Number(pt.lng ?? pt.longitude);
    if (Number.isNaN(mLat) || Number.isNaN(mLng)) return;

    const el = document.createElement("div");
    el.className = "custom-map-marker";
    el.style.width = "14px";
    el.style.height = "14px";
    el.style.borderRadius = "50%";
    el.style.backgroundColor = pt.color || "#2563eb";
    el.style.border = "2px solid #ffffff";
    el.style.boxShadow = "0 1px 3px rgba(0, 0, 0, 0.4)";
    el.style.cursor = "pointer";

    if (pt.label) el.title = pt.label;
    const mapMarker = new mapboxgl.Marker(el).setLngLat([mLng, mLat]);

    if (pt.label || pt.description) {
      const popupHTML = `<strong>${escapeHtml(pt.label || '点')}</strong>${pt.description ? `<br/>${escapeHtml(pt.description)}` : ''}`;
      const popup = new mapboxgl.Popup({ offset: 10, closeButton: false, closeOnClick: false }).setHTML(popupHTML);

      el.addEventListener("mouseenter", () => popup.setLngLat([mLng, mLat]).addTo(map));
      el.addEventListener("mouseleave", () => popup.remove());
    }
    mapMarker.addTo(map);
  });
}

function renderWeatherWidget(placeholder, props) {
  const { body } = createWidgetCard(placeholder, {
    title: props.location ? `天气 · ${props.location}` : "天气",
    icon: "fa-solid fa-cloud-sun",
  });
  const current = props.current || {};
  const currentEl = document.createElement("div");
  currentEl.className = "widget-weather-current";
  currentEl.innerHTML = `
    <span class="widget-weather-temp">${escapeHtml(String(current.temperature_c ?? "--"))}°C</span>
    <span class="widget-weather-meta">
      <span>${escapeHtml(String(current.condition ?? ""))}</span>
      ${current.humidity != null ? `<span>湿度 ${escapeHtml(String(current.humidity))}%</span>` : ""}
    </span>
  `;
  body.appendChild(currentEl);

  const forecast = Array.isArray(props.forecast) ? props.forecast : [];
  if (forecast.length) {
    const list = document.createElement("div");
    list.className = "widget-weather-forecast";
    list.innerHTML = forecast
      .map(
        (day) => `
          <div class="widget-weather-day">
            <span class="widget-weather-date">${escapeHtml(String(day.date ?? ""))}</span>
            <span class="widget-weather-cond">${escapeHtml(String(day.condition ?? ""))}</span>
            <span class="widget-weather-range">${escapeHtml(String(day.high_c ?? "--"))}° / ${escapeHtml(String(day.low_c ?? "--"))}°</span>
          </div>
        `
      )
      .join("");
    body.appendChild(list);
  }
}

function renderImageCarouselWidget(placeholder, props) {
  const { body } = createWidgetCard(placeholder, { title: "图片", icon: "fa-solid fa-images", fullscreen: true });
  const images = (Array.isArray(props.images) ? props.images : []).filter((img) => img && img.url);
  if (!images.length) {
    body.textContent = "暂无图片";
    return;
  }

  let index = 0;
  const stage = document.createElement("div");
  stage.className = "widget-carousel-stage";
  const img = document.createElement("img");
  img.className = "widget-carousel-img";
  img.loading = "lazy";
  const caption = document.createElement("div");
  caption.className = "widget-carousel-caption";

  const show = (next) => {
    index = (next + images.length) % images.length;
    img.src = images[index].url;
    img.alt = images[index].title || "";
    caption.textContent = `${images[index].title || ""} (${index + 1}/${images.length})`;
  };

  const prev = document.createElement("button");
  prev.type = "button";
  prev.className = "widget-carousel-nav prev";
  prev.innerHTML = `<i class="fa-solid fa-chevron-left"></i>`;
  prev.addEventListener("click", () => show(index - 1));

  const next = document.createElement("button");
  next.type = "button";
  next.className = "widget-carousel-nav next";
  next.innerHTML = `<i class="fa-solid fa-chevron-right"></i>`;
  next.addEventListener("click", () => show(index + 1));

  stage.appendChild(prev);
  stage.appendChild(img);
  stage.appendChild(next);
  body.appendChild(stage);
  body.appendChild(caption);
  show(0);
}

function renderUnknownWidget(placeholder, props, config) {
  const { body } = createWidgetCard(placeholder, { title: `未知卡片：${config.widget_type || "unknown"}`, icon: "fa-solid fa-puzzle-piece" });
  const pre = document.createElement("pre");
  pre.className = "widget-unknown-json";
  pre.textContent = JSON.stringify(props, null, 2);
  body.appendChild(pre);
}

const WIDGET_RENDERERS = {
  map: renderMapWidget,
  weather: renderWeatherWidget,
  image_carousel: renderImageCarouselWidget,
};

function eventRouteNode(event) {
  if (event.type === "run_start") return "orchestrator";
  if (event.type === "node_update") return event.node || event.details?.node || null;
  if (event.type === "tool_start" || event.type === "tool_end" || event.type === "tool_error" || event.type === "tool_message") return "tools";
  if (event.type === "run_complete") return "END";
  return null;
}

function routeEventsForCurrentRun(events) {
  const lastRunStartIndex = events.map((event) => event.type).lastIndexOf("run_start");
  return lastRunStartIndex >= 0 ? events.slice(lastRunStartIndex) : events;
}

function collectRouteTimeline(events) {
  const sequence = [];
  const eventSteps = new Map();

  for (const event of routeEventsForCurrentRun(events)) {
    const targetNode = eventRouteNode(event);
    if (!targetNode) continue;

    if (event.type === "run_start" && sequence.length === 0) {
      sequence.push("START");
    }

    if (sequence[sequence.length - 1] === targetNode) {
      eventSteps.set(event.id || `${event.type}-${event.time}`, sequence.length - 1);
      continue;
    }

    sequence.push(targetNode);
    eventSteps.set(event.id || `${event.type}-${event.time}`, sequence.length - 1);
  }

  return { sequence, eventSteps };
}

function calculateEventStepNumbers(events) {
  return collectRouteTimeline(events).eventSteps;
}

function renderEvents(events) {
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
          <div class="event-detail ${expanded ? "" : "hidden"}">${renderEventDetail(event)}</div>
        </div>
      `;
    })
    .join("");
}

function renderWorldStateDiff(currentWS, previousWS) {
  if (!currentWS || Object.keys(currentWS).length === 0) {
    return '<div class="empty">无世界状态信息。</div>';
  }
  previousWS = previousWS || {};

  const allKeys = Array.from(new Set([...Object.keys(currentWS), ...Object.keys(previousWS)])).sort();
  let html = '<div class="world-state-diff">';

  for (const key of allKeys) {
    const prevVal = previousWS[key];
    const currVal = currentWS[key];

    if (prevVal === undefined) {
      // Added
      html += `<div class="diff-line added">🟢 <strong>${escapeHtml(key)}</strong>: <pre class="diff-val">${escapeHtml(JSON.stringify(currVal, null, 2))}</pre></div>`;
    } else if (currVal === undefined) {
      // Deleted
      html += `<div class="diff-line deleted">🔴 <strong>${escapeHtml(key)}</strong>: <pre class="diff-val">${escapeHtml(JSON.stringify(prevVal, null, 2))}</pre></div>`;
    } else if (JSON.stringify(prevVal) !== JSON.stringify(currVal)) {
      // Modified
      html += `<div class="diff-line modified">
        🟡 <strong>${escapeHtml(key)}</strong>:
        <div class="diff-split">
          <span class="diff-old">${escapeHtml(JSON.stringify(prevVal, null, 2))}</span>
          &rarr;
          <span class="diff-new">${escapeHtml(JSON.stringify(currVal, null, 2))}</span>
        </div>
      </div>`;
    } else {
      // Unchanged
      html += `<div class="diff-line unchanged">⚪️ <strong>${escapeHtml(key)}</strong>: <span class="diff-val-compact">${escapeHtml(JSON.stringify(currVal))}</span></div>`;
    }
  }

  html += '</div>';
  return html;
}

function renderEventDetail(event) {
  const details = event.details && Object.keys(event.details).length ? event.details : event;
  const type = event.type || "";

  if (type === "llm_run" || type === "llm_token" || type === "llm_end") {
    const think = details.think || "";
    const msg = details.message || details.content || "";
    const prompt = details.prompts || [];
    const tokenCount = details.token_count || 0;
    const status = details.status || "completed";

    return `
      <div class="detail-grid">
        <div><span class="detail-label">状态</span><strong>${escapeHtml(statusLabel(status))}</strong></div>
        <div><span class="detail-label">Tokens</span><strong>${escapeHtml(tokenCount)}</strong></div>
      </div>
      ${prompt && prompt.length ? `
        <div class="detail-block">
          <div class="detail-label">📥 发送的 Message (Prompts)</div>
          <div class="orchestrator-prompts">
            ${prompt.map((p) => `
              <details class="orchestrator-prompt-details">
                <summary class="orchestrator-prompt-summary">
                  <span class="badge neutral">${escapeHtml(p.role || 'prompt')}</span>
                  <span class="prompt-summary-text">提示词 / 对话上下文</span>
                </summary>
                <pre class="detail-pre prompt-content">${escapeHtml(p.content)}</pre>
              </details>
            `).join("")}
          </div>
        </div>
      ` : ""}
      ${think ? `
        <div class="detail-block orchestrator-think-block">
          <div class="detail-label">🧠 LLM 思考过程 (Think)</div>
          <pre class="detail-pre orchestrator-think">${escapeHtml(think)}</pre>
        </div>
      ` : ""}
      ${msg ? `
        <div class="detail-block">
          <div class="detail-label">💬 LLM 输出结果 (Message)</div>
          <pre class="detail-pre orchestrator-message">${escapeHtml(msg)}</pre>
        </div>
      ` : ""}
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
    const nodeName = details.node || event.node || "-";
    const messages = update.messages || [];
    const toolCalls = messages.flatMap((message) => message.tool_calls || []);

    const activeSkills = update.active_skills || event.active_skills || (details && details.active_skills) || [];
    let skillsHtml = "";
    if (activeSkills.length) {
      skillsHtml = `
        <div class="active-skills-container">
          ${activeSkills.map(s => `
            <span class="skill-badge">
              <i class="fa-solid fa-lightbulb"></i> 关联技能 SOP: ${escapeHtml(s)}
            </span>
          `).join("")}
        </div>
      `;
    }

    if (nodeName === "memory") {
      const currentWS = update.world_state;
      let previousWS = null;
      if (currentState.events) {
        const idx = currentState.events.findIndex(e => e.id === event.id);
        if (idx !== -1) {
          for (let i = idx - 1; i >= 0; i--) {
            const ev = currentState.events[i];
            if (ev.type === "node_update" && (ev.node === "memory" || ev.details?.node === "memory")) {
              const prevUpdate = ev.details?.update || ev.update || {};
              if (prevUpdate.world_state) {
                previousWS = prevUpdate.world_state;
                break;
              }
            }
          }
        }
      }

      const diffHtml = renderWorldStateDiff(currentWS, previousWS);
      const stateFields = Object.keys(update).filter((key) => key !== "messages" && key !== "world_state");

      return `
        <div class="detail-grid">
          <div><span class="detail-label">节点</span><strong>${escapeHtml(nodeName)}</strong></div>
          <div><span class="detail-label">更新字段</span><strong>${escapeHtml(Object.keys(update).filter(k => k !== "messages").join(", ") || "-")}</strong></div>
        </div>
        <div class="detail-block">
          <div class="detail-label">🧠 世界状态变更 (World State Diff)</div>
          ${diffHtml}
        </div>
        ${stateFields.length ? `
          <div class="detail-block">
            <div class="detail-label">其他状态字段</div>
            <pre class="detail-pre compact">${escapeHtml(JSON.stringify(pickFields(update, stateFields), null, 2))}</pre>
          </div>
        ` : ""}
      `;
    }

    if (nodeName === "orchestrator" || nodeName === "evaluate") {
      const llmPrefix = nodeName === "orchestrator" ? "orchestrator" : "evaluator";
      const thinkKey = `${llmPrefix}_think`;
      const messageKey = `${llmPrefix}_message`;
      const promptKey = `${llmPrefix}_prompt`;
      const think = update[thinkKey] || "";
      const msg = update[messageKey] || "";
      const prompt = update[promptKey] || [];
      const stateFields = Object.keys(update).filter((key) => key !== "messages" && key !== thinkKey && key !== messageKey && key !== promptKey && key !== "active_skills");

      const currentFieldsObj = pickFields(update, stateFields);
      let previousFieldsObj = {};
      if (currentState.events) {
        const idx = currentState.events.findIndex(e => e.id === event.id);
        if (idx !== -1) {
          for (const key of stateFields) {
            for (let i = idx - 1; i >= 0; i--) {
              const ev = currentState.events[i];
              const evNode = ev.node || ev.details?.node;
              if (ev.type === "node_update" && evNode === nodeName) {
                const prevUpdate = ev.details?.update || ev.update || {};
                if (prevUpdate[key] !== undefined) {
                  previousFieldsObj[key] = prevUpdate[key];
                  break;
                }
              }
            }
          }
        }
      }
      const diffHtml = renderWorldStateDiff(currentFieldsObj, previousFieldsObj);

      return `
        ${skillsHtml}
        <div class="detail-grid">
          <div><span class="detail-label">节点</span><strong>${escapeHtml(nodeName)}</strong></div>
          <div><span class="detail-label">更新字段</span><strong>${escapeHtml(Object.keys(update).filter(k => k !== "messages").join(", ") || "-")}</strong></div>
        </div>
        ${prompt && prompt.length ? `
          <div class="detail-block">
            <div class="detail-label">📥 发送的 Message (Prompts)</div>
            <div class="orchestrator-prompts">
              ${prompt.map((p) => `
                <details class="orchestrator-prompt-details">
                  <summary class="orchestrator-prompt-summary">
                    <span class="badge neutral">${escapeHtml(p.role)}</span>
                    <span class="prompt-summary-text">${escapeHtml(p.role === 'system' ? '系统提示词' : '运行状态与历史上下文')}</span>
                  </summary>
                  <pre class="detail-pre prompt-content">${escapeHtml(p.content)}</pre>
                </details>
              `).join("")}
            </div>
          </div>
        ` : ""}
        ${think ? `
          <div class="detail-block orchestrator-think-block">
            <div class="detail-label">🧠 LLM 思考过程 (Think)</div>
            <pre class="detail-pre orchestrator-think">${escapeHtml(think)}</pre>
          </div>
        ` : ""}
        ${msg ? `
          <div class="detail-block">
            <div class="detail-label">💬 LLM 输出结果 (Message)</div>
            <pre class="detail-pre orchestrator-message">${escapeHtml(msg)}</pre>
          </div>
        ` : ""}
        ${stateFields.length ? `
          <div class="detail-block">
            <div class="detail-label">🧠 状态字段变更 (State Fields Diff)</div>
            ${diffHtml}
          </div>
        ` : ""}
      `;
    }

    if (nodeName === "agent") {
      const llmRun = details.llm_run || null;
      const stateFields = Object.keys(update).filter((key) => key !== "messages");

      let skillsPrependedHtml = skillsHtml;
      
      let llmHtml = "";
      if (llmRun) {
        const think = llmRun.think || "";
        const msg = llmRun.message || llmRun.content || "";
        const prompt = llmRun.prompts || [];
        const tokenCount = llmRun.token_count || 0;
        const status = llmRun.status || "completed";
        
        llmHtml = `
          <div class="agent-llm-section" style="margin-top: 12px; border-top: 1px dashed var(--border); padding-top: 12px;">
            <div class="detail-grid" style="margin-bottom: 8px;">
              <div><span class="detail-label">模型状态</span><strong>${escapeHtml(statusLabel(status))}</strong></div>
              <div><span class="detail-label">模型 Tokens</span><strong>${escapeHtml(tokenCount)}</strong></div>
            </div>
            ${prompt && prompt.length ? `
              <div class="detail-block">
                <div class="detail-label">📥 发送的 Message (Prompts)</div>
                <div class="orchestrator-prompts">
                  ${prompt.map((p) => `
                    <details class="orchestrator-prompt-details">
                      <summary class="orchestrator-prompt-summary">
                        <span class="badge neutral">${escapeHtml(p.role || 'prompt')}</span>
                        <span class="prompt-summary-text">提示词 / 对话上下文</span>
                      </summary>
                      <pre class="detail-pre prompt-content">${escapeHtml(p.content)}</pre>
                    </details>
                  `).join("")}
                </div>
              </div>
            ` : ""}
            ${think ? `
              <div class="detail-block orchestrator-think-block">
                <div class="detail-label">🧠 LLM 思考过程 (Think)</div>
                <pre class="detail-pre orchestrator-think">${escapeHtml(think)}</pre>
              </div>
            ` : ""}
            ${msg ? `
              <div class="detail-block">
                <div class="detail-label">💬 LLM 输出结果 (Message)</div>
                <pre class="detail-pre orchestrator-message">${escapeHtml(msg)}</pre>
              </div>
            ` : ""}
          </div>
        `;
      }
      
      return `
        ${skillsPrependedHtml}
        <div class="detail-grid">
          <div><span class="detail-label">节点</span><strong>${escapeHtml(nodeName)}</strong></div>
          ${stateFields.length ? `<div><span class="detail-label">更新字段</span><strong>${escapeHtml(stateFields.join(", ") || "messages")}</strong></div>` : ""}
        </div>
        ${messages.length ? `
          <div class="detail-block">
            <div class="detail-label">消息摘要</div>
            ${renderMessageSummary(messages)}
          </div>
        ` : ""}
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
        ${llmHtml}
      `;
    }

    const stateFields = Object.keys(update).filter((key) => key !== "messages");
    return `
      <div class="detail-grid">
        <div><span class="detail-label">节点</span><strong>${escapeHtml(nodeName)}</strong></div>
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

function renderApprovals(approvals) {
  if (!els.approvalList) return;
  if (!approvals || !approvals.length) {
    els.approvalList.className = "approval-list empty";
    els.approvalList.textContent = "暂无审批";
    return;
  }

  els.approvalList.className = "approval-list";
  els.approvalList.innerHTML = approvals
    .map((approval) => renderApprovalCard(approval))
    .join("");
}

function renderApprovalCard(approval) {
  const isFilesystemAccess = approval.type === "filesystem_access";
  const title = isFilesystemAccess
    ? `${approval.access === "write" ? "读写" : "读取"}本地目录: ${approval.host_path || "-"}`
    : (approval.target_uri || approval.target_path || "-");
  const subtitle = isFilesystemAccess
    ? `${approval.host_path || "-"} → ${approval.container_path || `/workspace/shared/${approval.name || ""}`}`
    : `${approval.source_path || "-"} → ${approval.target_uri || approval.target_path || "-"}`;
  const meta = isFilesystemAccess
    ? [`权限: ${approval.access || "read"}`, `名称: ${approval.name || "-"}`, approval.access === "write" ? "读写挂载" : "只读挂载"]
    : [approval.overwrite ? "覆盖写入" : "不覆盖", approval.target_exists ? "目标已存在" : "新文件", `${approval.source_size || "0"} bytes`];
  const approveText = isFilesystemAccess ? (approval.access === "write" ? "同意读写" : "同意读取") : "同意写回";
  return `
    <div class="approval-card" data-approval-id="${escapeHtml(approval.id)}">
      <div class="approval-card-header">
        <div>
          <div class="approval-title">${escapeHtml(title)}</div>
          <div class="approval-subtitle">${escapeHtml(subtitle)}</div>
        </div>
        <span class="badge pending">${statusLabel(approval.status || "pending")}</span>
      </div>
      <div class="approval-meta">
        ${meta.map((item) => `<span>${escapeHtml(item)}</span>`).join("")}
      </div>
      <details class="approval-preview">
        <summary>预览</summary>
        <pre>${escapeHtml(approval.preview || approval.summary || "")}</pre>
      </details>
      <div class="approval-actions">
        <button class="button primary approval-approve" type="button" data-approval-id="${escapeHtml(approval.id)}">${approveText}</button>
        <button class="button danger approval-reject" type="button" data-approval-id="${escapeHtml(approval.id)}">拒绝</button>
      </div>
    </div>
  `;
}

function routeLabel(route) {
  const labels = {
    START: "START",
    orchestrator: "Orchestrator",
    agent: "Agent",
    network_specialist_agent: "Network Specialist Agent",
    tools: "Tools",
    memory: "Memory",
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
  return collectRouteTimeline(state.events || []).sequence;
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

function buildRouteMermaidDefinition(active, visited, edgeLabels, llmActiveNode) {
  const nodeClasses = {
    S: mermaidNodeClass("START", active, visited),
    O: mermaidNodeClass("orchestrator", active, visited),
    A: mermaidNodeClass("agent", active, visited),
    N: mermaidNodeClass("network_specialist_agent", active, visited),
    E: mermaidNodeClass("evaluate", active, visited),
    X: mermaidNodeClass("END", active, visited),
    T: mermaidNodeClass("tools", active, visited),
    M: mermaidNodeClass("memory", active, visited),
    L: llmActiveNode ? "llmCallActive" : "visited",
  };

  const classLines = Object.entries(nodeClasses)
    .map(([node, className]) => `class ${node} ${className};`)
    .join("\n");
  const edges = [
    ["START->orchestrator", "S", "O", "solid"],
    ["orchestrator->memory", "O", "M", "solid"],
    ["memory->agent", "M", "A", "solid"],
    ["agent->memory", "A", "M", "solid"],
    ["memory->network_specialist_agent", "M", "N", "solid"],
    ["network_specialist_agent->memory", "N", "M", "solid"],
    ["memory->tools", "M", "T", "dotted"],
    ["tools->memory", "T", "M", "dotted"],
    ["memory->orchestrator", "M", "O", "solid"],
    ["memory->evaluate", "M", "E", "solid"],
    ["evaluate->END", "E", "X", "solid"],
    ["evaluate->orchestrator", "E", "O", "dotted"],
  ];
  const nodeSyntax = {
    S: 'S(["START"])',
    O: 'O["Orchestrator"]',
    A: 'A["Agent"]',
    N: 'N["Network Specialist Agent"]',
    E: 'E["Evaluator"]',
    X: 'X(["END"])',
    T: 'T["Tools"]',
    M: 'M["MemoryManager"]',
    L: 'L["<i class=\'fa-solid fa-brain\' style=\'font-size: 16px;\'></i>"]',
  };
  const edgeLines = edges.map(([key, from, to, style]) => {
    const label = edgeLabels.get(key)?.join(", ");
    const fromNode = nodeSyntax[from];
    const toNode = nodeSyntax[to];
    if (style === "dashed_llm") {
      return `  ${fromNode} -.-> ${toNode}`;
    }
    if (!label) {
      return `  ${fromNode} ${style === "dotted" ? "-.->" : "-->"} ${toNode}`;
    }
    if (style === "dotted") {
      return `  ${fromNode} -. ${label} .-> ${toNode}`;
    }
    return `  ${fromNode} -->|${label}| ${toNode}`;
  }).join("\n");
  const linkStyles = edges
    .map(([key, from, to, style], index) => {
      if (style === "dashed_llm") {
        const isActive = (from === "O" && llmActiveNode === "orchestrator") ||
                         (from === "A" && llmActiveNode === "agent") ||
                         (from === "E" && llmActiveNode === "evaluate");
        return isActive ? `  linkStyle ${index} stroke:#15803d,stroke-width:3px;` : "";
      }
      return edgeLabels.has(key) ? `  linkStyle ${index} stroke:#2563eb,stroke-width:3px;` : "";
    })
    .filter(Boolean)
    .join("\n");

  return `
flowchart TD
${edgeLines}
  ${nodeSyntax.L}

  classDef idle fill:#f3f6fa,stroke:#d9e1ec,color:#667085,stroke-width:1px;
  classDef visited fill:#eaf1ff,stroke:#bdd2fb,color:#2563eb,stroke-width:1.5px;
  classDef active fill:#e8f7ee,stroke:#15803d,color:#15803d,stroke-width:1.5px;
  classDef llmCallActive fill:#e8f7ee,stroke:#15803d,color:#15803d,stroke-width:1.5px,stroke-dasharray: 5 5;
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
          securityLevel: "loose",
          theme: "base",
          flowchart: {
            curve: "basis",
            htmlLabels: true,
            nodeSpacing: 18,
            rankSpacing: 22,
          },
          themeVariables: {
            fontFamily: "Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif",
            fontSize: "10px",
            labelFontSize: "9px",
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
    // Use a unique ID for each render to prevent DOM collisions during concurrent runs
    const { svg } = await mermaid.render("routeGraph_" + version, definition);
    if (version !== routeRenderVersion) return;
    const diagram = els.routeList.querySelector(".route-diagram");
    if (diagram) {
      diagram.innerHTML = svg;
      fitRouteDiagramToContainer();
      diagram.classList.remove("loading");
    }
  } catch (error) {
    lastRenderedDefinition = ""; // Reset on error to allow retry
    const notice = els.routeList.querySelector(".route-library-error");
    if (notice) {
      notice.textContent = `Mermaid 加载失败：${error.message}`;
      notice.classList.remove("hidden");
    }
  }
}


let activeModelConfig = null;

function getStoredModelConfig() {
  try {
    const raw = localStorage.getItem(MODEL_CONFIG_STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    localStorage.removeItem(MODEL_CONFIG_STORAGE_KEY);
    return null;
  }
}

function setModelConfigBadge(config, source = "server") {
  if (!els.modelConfigBadge || !config) return;
  const provider = providerLabel(config.provider || "openai");
  const model = config.model_name || "未设置";
  els.modelConfigBadge.textContent = `${source === "local" ? "自定义" : "服务端默认"}: ${provider} / ${model}`;
  els.modelConfigBadge.className = `badge success model-config-badge ${source === "local" ? "custom" : "server"}`;
}

function providerLabel(provider) {
  const labels = {
    openai: "OpenAI",
    deepseek: "DeepSeek",
    ollama: "Ollama",
    llamacpp: "llama.cpp",
    custom: "Custom",
  };
  return labels[provider] || provider || "-";
}

function modelPresetsFor(provider) {
  return MODEL_PRESETS[provider] || [];
}

function shouldUseCustomModelInput() {
  return !els.modelPresetSelect || els.modelPresetSelect.value === "__custom__";
}

function selectedModelName() {
  if (!els.modelPresetSelect || els.modelPresetSelect.value === "__custom__") {
    return els.modelNameInput.value.trim();
  }
  return els.modelPresetSelect.value;
}

function updateCustomModelVisibility() {
  if (!els.modelNameField) return;
  const isCustom = shouldUseCustomModelInput();
  els.modelNameField.classList.toggle("hidden", !isCustom);
  if (!isCustom) {
    els.modelNameInput.value = els.modelPresetSelect.value;
  }
}

function populateModelPresets(provider, selectedModel = "") {
  if (!els.modelPresetSelect) return;
  const presets = modelPresetsFor(provider);
  const usesPreset = selectedModel && presets.includes(selectedModel);
  els.modelPresetSelect.innerHTML = presets
    .map((model) => `<option value="${escapeHtml(model)}">${escapeHtml(model)}</option>`)
    .join("") + `<option value="__custom__">自定义...</option>`;
  els.modelPresetSelect.value = usesPreset ? selectedModel : "__custom__";
}

function applyModelConfig(config, source = "server") {
  if (!els.modelConfigForm || !config) return;
  const provider = config.provider || "openai";
  const modelName = config.model_name || "";
  const defaultBaseUrls = config.default_base_urls || PROVIDER_DEFAULT_BASE_URLS;
  const defaultModelNames = config.default_model_names || PROVIDER_DEFAULT_MODEL_NAMES;
  Object.assign(PROVIDER_DEFAULT_BASE_URLS, defaultBaseUrls);
  Object.assign(PROVIDER_DEFAULT_MODEL_NAMES, defaultModelNames);

  activeModelConfig = { ...config, source };
  els.modelProviderSelect.value = provider;
  populateModelPresets(provider, modelName);
  els.modelNameInput.value = modelName;
  els.modelBaseUrlInput.value = config.base_url || PROVIDER_DEFAULT_BASE_URLS[provider] || "";
  els.modelApiKeyInput.value = config.api_key || "";
  els.modelApiKeyInput.placeholder = config.api_key_set ? "服务端已配置，留空使用服务端" : "可选，仅保存在浏览器";
  updateCustomModelVisibility();
  setModelConfigBadge(activeModelConfig, source);
}

function buildModelConfigFromForm() {
  return {
    provider: els.modelProviderSelect.value,
    model_name: selectedModelName(),
    base_url: els.modelBaseUrlInput.value.trim(),
    api_key: els.modelApiKeyInput.value,
  };
}

function saveModelConfig() {
  if (!els.modelConfigForm) return;
  const payload = buildModelConfigFromForm();
  if (!payload.model_name) {
    alert("模型名称必填");
    els.modelNameInput.focus();
    return;
  }
  localStorage.setItem(MODEL_CONFIG_STORAGE_KEY, JSON.stringify(payload));
  applyModelConfig(payload, "local");
}

async function loadWebConfig() {
  try {
    const response = await fetch("/api/web-config", { headers: sessionHeaders() });
    if (!response.ok) return;
    const config = await response.json();
    if (typeof config.mapbox_access_token === "string") {
      mapboxAccessToken = config.mapbox_access_token;
    }
  } catch (error) {
    // Non-fatal: map widgets will show a "token not configured" message.
  } finally {
    while (pendingMapWidgets.length) {
      const retry = pendingMapWidgets.shift();
      try {
        retry();
      } catch (error) {
        /* ignore individual widget retry failures */
      }
    }
  }
}

async function loadModelConfig() {
  if (!els.modelConfigForm) return;
  try {
    const response = await fetch("/api/model-config", { headers: sessionHeaders() });
    const serverConfig = await response.json();
    if (!response.ok) {
      setModelConfigBadge({ provider: "custom", model_name: serverConfig.detail || "加载失败" }, "server");
      return;
    }
    const localConfig = getStoredModelConfig();
    const config = localConfig
      ? { ...serverConfig, ...localConfig, default_base_urls: serverConfig.default_base_urls, providers: serverConfig.providers }
      : serverConfig;
    applyModelConfig(config, localConfig ? "local" : "server");
  } catch (error) {
    setModelConfigBadge({ provider: "custom", model_name: `加载失败：${error.message}` }, "server");
  }
}

function activeModelPayload() {
  if (!activeModelConfig) {
    return null;
  }
  return {
    provider: activeModelConfig.provider,
    model_name: activeModelConfig.model_name,
    base_url: activeModelConfig.base_url || "",
    api_key: activeModelConfig.api_key || "",
  };
}

function renderRoutes(state) {
  const active = state.current_node || "";
  const visited = collectVisitedRoutes(state);
  const edgeLabels = collectRouteEdgeLabels(state);
  const mermaidDefinition = buildRouteMermaidDefinition(active, visited, edgeLabels, state.llm_active_node);

  // Skip rendering if the definition has not changed
  if (mermaidDefinition === lastRenderedDefinition) {
    fitRouteDiagramToContainer();
    return;
  }
  lastRenderedDefinition = mermaidDefinition;

  const renderVersion = ++routeRenderVersion;

  els.routeList.innerHTML = `
    <div class="route-diagram loading">正在加载 Mermaid 流程图...</div>
    <div class="route-library-error hidden"></div>
  `;
  renderMermaidRouteDiagram(mermaidDefinition, renderVersion);
}

function renderState(state, isStream = false) {
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

async function decideApproval(approvalId, action) {
  const response = await fetch(`/api/approvals/${action}?session_id=${encodeURIComponent(sessionId)}`, {
    method: "POST",
    headers: sessionHeaders(),
    body: JSON.stringify({ approval_id: approvalId }),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    alert(payload.detail || "审批操作失败");
    return;
  }
  if (payload.state) {
    renderState(payload.state);
  } else {
    await loadState();
  }
}

function connectWs() {
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${protocol}://${window.location.host}/ws?session_id=${encodeURIComponent(sessionId)}`);

  ws.addEventListener("open", () => {
    setBadge(els.connectionBadge, "已连接", "success");
  });

let streamBuffer = "";
  let streamTimeout = null;

  ws.addEventListener("message", (message) => {
    try {
      const payload = JSON.parse(message.data);
      if (payload.state) {
        renderState(payload.state);
      } else if (payload.type === "stream") {
        let textToAppend = payload.content || "";
        if (payload.token_type === "thinking") {
            const currentText = (currentState.model_output || "") + streamBuffer;
            const lastThink = currentText.lastIndexOf("<think>");
            const lastThinkClose = currentText.lastIndexOf("</think>");
            const isThinkOpen = (lastThink !== -1) && (lastThinkClose === -1 || lastThink > lastThinkClose);
            if (!isThinkOpen) {
                textToAppend = "<think>" + textToAppend;
            }
        } else if (payload.token_type === "content") {
            const currentText = (currentState.model_output || "") + streamBuffer;
            const lastThink = currentText.lastIndexOf("<think>");
            const lastThinkClose = currentText.lastIndexOf("</think>");
            const isThinkOpen = (lastThink !== -1) && (lastThinkClose === -1 || lastThink > lastThinkClose);
            if (isThinkOpen) {
                textToAppend = "</think>" + textToAppend;
            }
        }
        
        streamBuffer += textToAppend;
        if (!streamTimeout) {
          streamTimeout = setTimeout(() => {
            renderState({ model_output: (currentState.model_output || "") + streamBuffer }, true);
            streamBuffer = "";
            streamTimeout = null;
          }, 200);
        }
      }
    } catch (error) {
      console.error("Failed to render websocket update", error);
      loadState().catch((loadError) => console.error("Failed to reload state after websocket error", loadError));
    }
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

  const previousState = currentState;
  const optimisticState = {
    ...currentState,
    status: "running",
    current_node: "orchestrator",
    task_complexity: "unknown",
    todo_list: [],
    model_output: "",
    tool_runs: [],
    events: [],
    context_tags: ["general"],
    world_state: {},
    messages: [
      ...(currentState.messages || []),
      { role: "user", content: message, tool_calls: [] },
    ],
  };
  els.messageInput.value = "";
  renderState(optimisticState);

  try {
    const response = await fetch(`/api/chat?session_id=${encodeURIComponent(sessionId)}`, {
      method: "POST",
      headers: sessionHeaders(),
      body: JSON.stringify({ message, model_config: activeModelPayload() }),
    });

    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      renderState(previousState);
      els.messageInput.value = message;
      alert(payload.detail || "发送失败");
      return;
    }

    if (payload.state) {
      renderState(payload.state);
    } else {
      await loadState();
    }
  } catch (error) {
    renderState(previousState);
    els.messageInput.value = message;
    alert(`发送失败：${error.message}`);
  }
});

if (els.modelProviderSelect) {
  els.modelProviderSelect.addEventListener("change", () => {
    const provider = els.modelProviderSelect.value;
    const presets = modelPresetsFor(provider);
    const nextModel = PROVIDER_DEFAULT_MODEL_NAMES[provider] || presets[0] || "";
    populateModelPresets(provider, nextModel);
    els.modelNameInput.value = nextModel;
    els.modelBaseUrlInput.value = PROVIDER_DEFAULT_BASE_URLS[provider] || "";
    updateCustomModelVisibility();
  });
}

if (els.modelPresetSelect) {
  els.modelPresetSelect.addEventListener("change", () => {
    updateCustomModelVisibility();
    if (els.modelPresetSelect.value === "__custom__") {
      els.modelNameInput.focus();
      els.modelNameInput.select();
    }
  });
}

if (els.modelConfigForm) {
  els.modelConfigForm.addEventListener("submit", (event) => {
    event.preventDefault();
    saveModelConfig();
  });
}

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

if (els.approvalList) {
  els.approvalList.addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-approval-id]");
    if (!button) return;
    const approvalId = button.dataset.approvalId;
    const action = button.classList.contains("approval-approve") ? "approve" : "reject";
    button.disabled = true;
    await decideApproval(approvalId, action);
  });
}

els.clearBtn.addEventListener("click", async () => {
  await fetch(`/api/clear?session_id=${encodeURIComponent(sessionId)}`, {
    method: "POST",
    headers: sessionHeaders(),
  });
  await loadState();
});

els.newSessionBtn.addEventListener("click", () => {
  if (confirm("确定要新建会话吗？当前会话的所有未保存进度将会丢失。")) {
    localStorage.removeItem(SESSION_STORAGE_KEY);
    location.reload();
  }
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
  renderEvents(currentState.events || []);
});

initializeProgressSplitResizer();
loadWebConfig();
loadModelConfig();
loadState();

if (els.toggleRuntimeBtn) {
  els.toggleRuntimeBtn.addEventListener("click", () => {
    els.workspace.classList.toggle("runtime-collapsed");
    setTimeout(() => window.dispatchEvent(new Event('resize')), 300);
  });
}

connectWs();
