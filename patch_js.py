with open("/Users/zhaoyu/Documents/agent-framework/app/web_static/app.js", "r") as f:
    content = f.read()

injection = """
// Force inject button if it doesn't exist
const runtimeHeader = document.querySelector(".runtime-panel .panel-header");
if (runtimeHeader && !document.getElementById("toggleRuntimeBtn")) {
    runtimeHeader.style.display = "flex";
    runtimeHeader.style.justifyContent = "space-between";
    runtimeHeader.style.width = "100%";
    
    // Wrap existing content
    const titleWrap = document.createElement("div");
    titleWrap.className = "runtime-header-title";
    titleWrap.style.display = "flex";
    titleWrap.style.alignItems = "center";
    titleWrap.style.gap = "8px";
    
    // Move h2 and badge into wrapper
    const h2 = runtimeHeader.querySelector("h2");
    const badge = document.getElementById("nodeBadge");
    if (h2) titleWrap.appendChild(h2);
    if (badge) titleWrap.appendChild(badge);
    runtimeHeader.appendChild(titleWrap);
    
    // Add button
    const btn = document.createElement("button");
    btn.id = "toggleRuntimeBtn";
    btn.className = "button ghost";
    btn.style.padding = "4px 8px";
    btn.style.fontSize = "14px";
    btn.innerHTML = '>';
    runtimeHeader.appendChild(btn);
    
    els.toggleRuntimeBtn = btn;
}

if (els.toggleRuntimeBtn) {
    els.toggleRuntimeBtn.addEventListener("click", () => {
        els.workspace.classList.toggle("runtime-collapsed");
        setTimeout(() => window.dispatchEvent(new Event('resize')), 300);
    });
}
// Ensure workspace has collapsed class initially
if (!els.workspace.classList.contains("runtime-collapsed")) {
    els.workspace.classList.add("runtime-collapsed");
}
"""

# Replace the existing event listener
import re
content = re.sub(r'els\.toggleRuntimeBtn\.addEventListener.*}\);', injection, content, flags=re.DOTALL)

with open("/Users/zhaoyu/Documents/agent-framework/app/web_static/app.js", "w") as f:
    f.write(content)

print("JS Patched!")
