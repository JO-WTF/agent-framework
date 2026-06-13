with open("/Users/zhaoyu/Documents/agent-framework/app/web_static/app.js", "r") as f:
    content = f.read()

css_injection = """
// Force inject CSS
if (!document.getElementById("runtime-panel-style")) {
    const style = document.createElement("style");
    style.id = "runtime-panel-style";
    style.textContent = `
    .workspace.runtime-collapsed {
      grid-template-columns: minmax(280px, 2.25fr) 48px minmax(320px, 0.95fr) !important;
    }
    .workspace.runtime-collapsed .runtime-panel {
      overflow: hidden !important;
    }
    .workspace.runtime-collapsed .runtime-panel > :not(.panel-header) {
      display: none !important;
    }
    .workspace.runtime-collapsed .runtime-panel .panel-header .runtime-header-title {
      display: none !important;
    }
    .workspace.runtime-collapsed .runtime-panel .panel-header {
      justify-content: center !important;
      padding: 8px 0 !important;
    }
    .workspace.runtime-collapsed #toggleRuntimeBtn i,
    .workspace.runtime-collapsed #toggleRuntimeBtn {
      transform: rotate(180deg) !important;
    }
    `;
    document.head.appendChild(style);
}
"""

if "runtime-panel-style" not in content:
    content += "\n" + css_injection

with open("/Users/zhaoyu/Documents/agent-framework/app/web_static/app.js", "w") as f:
    f.write(content)

print("Injected CSS via JS")
