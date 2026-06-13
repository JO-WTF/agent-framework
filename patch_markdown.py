import re

with open("/Users/zhaoyu/Documents/agent-framework/app/web_static/app.js", "r") as f:
    content = f.read()

start = content.find("function renderAssistantMarkdown(content) {")
end = content.find("function messageBlocks(message) {", start)

old_render = content[start:end]

new_render = """function renderAssistantMarkdown(content) {
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

"""

content = content.replace(old_render, new_render)

with open("/Users/zhaoyu/Documents/agent-framework/app/web_static/app.js", "w") as f:
    f.write(content)

print("Fixed renderAssistantMarkdown")
