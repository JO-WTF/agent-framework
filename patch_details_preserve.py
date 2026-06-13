import re

with open("/Users/zhaoyu/Documents/agent-framework/app/web_static/app.js", "r") as f:
    content = f.read()

old_logic = """    const existingWidgets = new Map();
    node.querySelectorAll(".chat-widget").forEach(w => {
      if (w.dataset.hydrated) {
        existingWidgets.set(w.dataset.widget, w);
      }
    });
    
    node.className = `message ${role}`;
    node.dataset.sig = sig;
    node.innerHTML = inner;"""

new_logic = """    const existingWidgets = new Map();
    node.querySelectorAll(".chat-widget").forEach(w => {
      if (w.dataset.hydrated) {
        existingWidgets.set(w.dataset.widget, w);
      }
    });
    
    const existingDetails = [];
    node.querySelectorAll("details.chat-think-details").forEach(d => {
      existingDetails.push(d.open);
    });
    
    node.className = `message ${role}`;
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
    });"""

content = content.replace(old_logic, new_logic)

with open("/Users/zhaoyu/Documents/agent-framework/app/web_static/app.js", "w") as f:
    f.write(content)

print("Applied details state preservation patch")
