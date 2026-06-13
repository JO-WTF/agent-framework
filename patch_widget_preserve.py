import re

with open("/Users/zhaoyu/Documents/agent-framework/app/web_static/app.js", "r") as f:
    content = f.read()

old_logic = """    if (!node) {
      node = document.createElement("div");
      els.messageList.appendChild(node);
    }
    
    node.className = `message ${role}`;
    node.dataset.sig = sig;
    node.innerHTML = inner;
    hydrateWidgets(node);"""

new_logic = """    if (!node) {
      node = document.createElement("div");
      els.messageList.appendChild(node);
    }

    const existingWidgets = new Map();
    node.querySelectorAll(".chat-widget").forEach(w => {
      if (w.dataset.hydrated) {
        existingWidgets.set(w.dataset.widget, w);
      }
    });
    
    node.className = `message ${role}`;
    node.dataset.sig = sig;
    node.innerHTML = inner;

    node.querySelectorAll(".chat-widget").forEach(w => {
      const saved = existingWidgets.get(w.dataset.widget);
      if (saved) {
        w.parentNode.replaceChild(saved, w);
      }
    });

    hydrateWidgets(node);"""

content = content.replace(old_logic, new_logic)

with open("/Users/zhaoyu/Documents/agent-framework/app/web_static/app.js", "w") as f:
    f.write(content)

print("Applied widget preservation patch")
