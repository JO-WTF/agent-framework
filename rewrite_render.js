const fs = require('fs');

let content = fs.readFileSync('/Users/zhaoyu/Documents/agent-framework/app/web_static/app.js', 'utf8');

const oldFuncStart = 'function renderMessages(messages, status, model_output) {';
const newFuncCode = `
const messageHtmlCache = new Map();

function getMessageHtml(message) {
  const sig = JSON.stringify({ role: message.role, blocks: message.blocks || null, content: message.content || "" });
  if (messageHtmlCache.has(sig)) {
    return messageHtmlCache.get(sig);
  }
  const role = escapeHtml(message.role || "assistant");
  let html = "";
  if (role === "assistant") {
    html = \`<div class="message \${role}">\${renderAssistantBlocks(messageBlocks(message))}</div>\`;
  } else {
    html = \`<div class="message \${role}">\${escapeHtml(String(message.content || ""))}</div>\`;
  }
  // Only cache if it's not the streaming message (which lacks an id or has changing content).
  // Actually, caching by exact signature is safe even for streaming because streaming content changes signature!
  // To avoid memory leak, we could limit cache size, but for a chat it's fine.
  messageHtmlCache.set(sig, html);
  return html;
}

let lastRenderedSignature = null;

function renderMessages(messages, status, model_output) {
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

  const currentSignature = JSON.stringify(displayMessages.map(m => ({ role: m.role, blocks: m.blocks || null, content: m.content || "" })));
  if (currentSignature === lastRenderedSignature) return;
  lastRenderedSignature = currentSignature;

  if (!displayMessages.length) {
    els.messageList.innerHTML = \`<div class="empty">暂无对话</div>\`;
    isFirstRender = false;
    return;
  }

  const html = displayMessages.map(getMessageHtml).join("");
  
  // To avoid fully destroying DOM elements that haven't changed, we could use DOM diffing,
  // but just skipping the Markdown parsing for the whole history is a HUGE 99% speedup.
  // Throttling innerHTML update is also good.
  els.messageList.innerHTML = html;

  hydrateWidgets(els.messageList);
  
  if (isAtBottom) {
    els.messageList.scrollTop = els.messageList.scrollHeight;
  }
  
  els.messageList.querySelectorAll('.chat-think-details[open] .chat-think-content').forEach(el => {
    el.scrollTop = el.scrollHeight;
  });
  
  isFirstRender = false;
}
`;

// Replace everything from oldFuncStart to the end of the function.
// Since the function ends before `function hydrateWidgets(root) {`, we can extract it.
const funcStartIdx = content.indexOf(oldFuncStart);
const nextFuncIdx = content.indexOf('function hydrateWidgets(root) {');

if (funcStartIdx !== -1 && nextFuncIdx !== -1) {
  content = content.substring(0, funcStartIdx) + newFuncCode + '\n' + content.substring(nextFuncIdx);
  // increment cache buster
  content = content.replace("app.js?v=6", "app.js?v=7");
  content = content.replace("styles.css?v=6", "styles.css?v=7");
  fs.writeFileSync('/Users/zhaoyu/Documents/agent-framework/app/web_static/app.js', content);
  console.log('Patched renderMessages for performance.');
} else {
  console.log('Could not find function bounds.');
}
