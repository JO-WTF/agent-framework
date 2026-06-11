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
  modelOutput: document.getElementById("modelOutput"),
  eventList: document.getElementById("eventList"),
  todoList: document.getElementById("todoList"),
  approvalList: document.getElementById("approvalList"),
  routeList: document.getElementById("routeList"),
  progressSplit: document.getElementById("progressSplit"),
  progressResizeHandle: document.getElementById("progressResizeHandle"),
  complexityValue: document.getElementById("complexityValue"),
  currentNodeValue: document.getElementById("currentNodeValue"),
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
let mapboxConfigPromise;

const expandedEvents = new Set();
const ROUTE_GROUPS = [
  ["START", "orchestrator", "memory", "agent", "memory", "orchestrator", "memory", "evaluate", "END"],
  ["agent", "memory", "tools", "memory", "orchestrator"],
  ["evaluate", "orchestrator"],
];
let mermaidModulePromise;
let routeRenderVersion = 0;
let lastRenderedDefinition = "";
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
  map_cards: [],
};


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
    map_card: "地图卡片",
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
  const { think, message } = parseThinkingContent(content);
  let html = "";
  if (think) {
    html += `
      <details class="chat-think-details" open>
        <summary class="chat-think-summary">🧠 思考过程 (点击收起/展开)</summary>
        <div class="chat-think-content">${escapeHtml(think)}</div>
      </details>
    `;
  }
  if (message) {
    html += DOMPurify.sanitize(marked.parse(message), {
      USE_PROFILES: { html: true, mathMl: true },
      ADD_ATTR: ["class", "style", "xmlns"]
    });
  } else if (!think) {
    html += escapeHtml(content);
  }
  return html;
}



function mapboxConfig() {
  if (!mapboxConfigPromise) {
    mapboxConfigPromise = fetch(`/api/mapbox-config?session_id=${encodeURIComponent(sessionId)}`, { headers: sessionHeaders() })
      .then((response) => response.ok ? response.json() : { configured: false, token: "" })
      .catch(() => ({ configured: false, token: "" }));
  }
  return mapboxConfigPromise;
}

function coordinateLabel(point) {
  const lat = Number(point.latitude);
  const lng = Number(point.longitude);
  if (!Number.isFinite(lat) || !Number.isFinite(lng)) return "";
  return `${lat.toFixed(6)}, ${lng.toFixed(6)}`;
}

function renderMapCards(mapCards) {
  const cards = Array.isArray(mapCards) ? mapCards : [];
  if (!cards.length) return "";
  return cards.map((card) => {
    const id = escapeHtml(card.id || crypto.randomUUID?.() || `map-${Math.random()}`);
    const points = Array.isArray(card.points) ? card.points : [];
    const lines = Array.isArray(card.lines) ? card.lines : [];
    return `
      <div class="message assistant map-card-message">
        <div class="map-card-header">
          <div>
            <div class="map-card-title">🗺️ ${escapeHtml(card.title || "地图展示")}</div>
            ${card.note ? `<div class="map-card-note">${escapeHtml(card.note)}</div>` : ""}
          </div>
          <span class="badge neutral">${points.length} 点 / ${lines.length} 线</span>
        </div>
        <div id="${id}" class="map-card-map" data-map-card-id="${escapeHtml(card.id || "")}">正在加载地图...</div>
        ${points.length ? `
          <div class="map-card-points">
            ${points.slice(0, 8).map((point) => `
              <span title="${escapeHtml(coordinateLabel(point))}">${escapeHtml(point.label || point.id || "点")}</span>
            `).join("")}
            ${points.length > 8 ? `<span>+${points.length - 8}</span>` : ""}
          </div>
        ` : ""}
      </div>
    `;
  }).join("");
}

function initializeMapCards(mapCards) {
  const cards = Array.isArray(mapCards) ? mapCards : [];
  if (!cards.length) return;

  mapboxConfig().then((config) => {
    for (const card of cards) {
      const container = document.querySelector(`[data-map-card-id="${CSS.escape(String(card.id || ""))}"]`);
      if (!container || container.dataset.initialized === "true") continue;
      if (!config.configured || !config.token) {
        container.classList.add("unavailable");
        container.innerHTML = `
          <div>
            <strong>未配置 Mapbox 地图 Token</strong>
            <p>请在服务端环境变量中设置 <code>MAPBOX_PUBLIC_TOKEN</code>（或 MAPBOX_ACCESS_TOKEN / MAPBOX_API_KEY），然后刷新页面。</p>
          </div>
        `;
        container.dataset.initialized = "true";
        continue;
      }
      if (!window.mapboxgl) {
        container.classList.add("unavailable");
        container.textContent = "Mapbox GL JS 加载失败，请检查网络或浏览器控制台。";
        container.dataset.initialized = "true";
        continue;
      }
      try {
        window.mapboxgl.accessToken = config.token;
        const points = Array.isArray(card.points) ? card.points : [];
        const lines = Array.isArray(card.lines) ? card.lines : [];
        const center = card.center || points[0] || { latitude: 31.2304, longitude: 121.4737 };
        const map = new window.mapboxgl.Map({
          container,
          style: "mapbox://styles/mapbox/streets-v12",
          center: [Number(center.longitude), Number(center.latitude)],
          zoom: Number.isFinite(Number(card.zoom)) ? Number(card.zoom) : 10,
        });
        map.addControl(new window.mapboxgl.NavigationControl({ showCompass: false }), "top-right");

        const bounds = new window.mapboxgl.LngLatBounds();
        let hasBounds = false;
        for (const point of points) {
          const lat = Number(point.latitude);
          const lng = Number(point.longitude);
          if (!Number.isFinite(lat) || !Number.isFinite(lng)) continue;
          const popupHtml = `
            <strong>${escapeHtml(point.label || point.id || "点")}</strong><br/>
            <span>${escapeHtml(point.description || coordinateLabel(point))}</span>
          `;
          new window.mapboxgl.Marker({ color: point.color || "#2563eb" })
            .setLngLat([lng, lat])
            .setPopup(new window.mapboxgl.Popup({ offset: 16 }).setHTML(popupHtml))
            .addTo(map);
          bounds.extend([lng, lat]);
          hasBounds = true;
        }

        map.on("load", () => {
          lines.forEach((line, index) => {
            const coordinates = Array.isArray(line.coordinates) ? line.coordinates : [];
            if (coordinates.length < 2) return;
            const sourceId = `${card.id || "map"}-line-${index}`;
            map.addSource(sourceId, {
              type: "geojson",
              data: {
                type: "Feature",
                properties: { label: line.label || `线路 ${index + 1}` },
                geometry: { type: "LineString", coordinates },
              },
            });
            map.addLayer({
              id: sourceId,
              type: "line",
              source: sourceId,
              paint: {
                "line-color": line.color || "#f97316",
                "line-width": 4,
                "line-opacity": 0.82,
              },
            });
            coordinates.forEach((coord) => {
              if (Array.isArray(coord) && coord.length >= 2) {
                bounds.extend([Number(coord[0]), Number(coord[1])]);
                hasBounds = true;
              }
            });
          });
          if (hasBounds && !Number.isFinite(Number(card.zoom))) {
            map.fitBounds(bounds, { padding: 48, maxZoom: 13, duration: 0 });
          }
        });
        container.dataset.initialized = "true";
      } catch (error) {
        container.classList.add("unavailable");
        container.textContent = `地图渲染失败：${error.message}`;
        container.dataset.initialized = "true";
      }
    }
  });
}

function renderMessages(messages, mapCards = []) {
  if (!messages.length && !(mapCards || []).length) {
    els.messageList.innerHTML = `<div class="empty">暂无对话</div>`;
    return;
  }

  const messageHtml = messages
    .map((message) => {
      const role = escapeHtml(message.role || "assistant");
      const rawContent = String(message.content || "");
      const content = role === "assistant"
        ? renderAssistantMarkdown(rawContent)
        : escapeHtml(rawContent);
      return `<div class="message ${role}">${content}</div>`;
    })
    .join("");
  els.messageList.innerHTML = `${messageHtml}${renderMapCards(mapCards)}`;
  initializeMapCards(mapCards);
  els.messageList.scrollTop = els.messageList.scrollHeight;
}

function eventRouteNode(event) {
  if (event.type === "run_start") return "orchestrator";
  if (event.type === "node_update") return event.node || event.details?.node || null;
  if (event.type === "tool_start" || event.type === "tool_end" || event.type === "tool_error" || event.type === "tool_message" || event.type === "map_card") return "tools";
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


  if (type === "map_card") {
    const card = details.card || {};
    return `
      <div class="detail-kv">
        <div class="detail-kv-row"><span>标题</span><strong>${escapeHtml(card.title || "地图展示")}</strong></div>
        <div class="detail-kv-row"><span>点</span><strong>${escapeHtml((card.points || []).length)}</strong></div>
        <div class="detail-kv-row"><span>线</span><strong>${escapeHtml((card.lines || []).length)}</strong></div>
        <div class="detail-kv-row detail-kv-row-block"><span>卡片 JSON</span><pre class="detail-pre">${escapeHtml(JSON.stringify(card, null, 2))}</pre></div>
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

function renderState(state) {
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
  els.modelOutput.innerHTML = renderModelOutput(state.model_output || "");
  els.modelOutput.scrollTop = els.modelOutput.scrollHeight;

  renderMessages(state.messages || [], state.map_cards || []);
  renderEvents(state.events || []);
  renderApprovals(state.world_state?.pending_approvals || []);
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

  ws.addEventListener("message", (message) => {
    try {
      const payload = JSON.parse(message.data);
      if (payload.state) {
        renderState(payload.state);
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
    map_cards: currentState.map_cards || [],
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
  loadState();
});

initializeProgressSplitResizer();
loadModelConfig();
loadState();
connectWs();
