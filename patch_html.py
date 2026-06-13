with open("/Users/zhaoyu/Documents/agent-framework/app/web_static/index.html", "r") as f:
    content = f.read()

old_html = """        <section class="panel runtime-panel">
          <div class="panel-header" style="justify-content: space-between; display: flex; width: 100%;">
            <div style="display: flex; align-items: center; gap: 8px;" class="runtime-header-title">
              <h2>实时运行</h2>
              <span id="nodeBadge" class="badge neutral">无节点</span>
            </div>
            <button id="toggleRuntimeBtn" class="button ghost" style="padding: 4px 8px; font-size: 14px;" title="收起/展开">❯</button>
          </div>"""

new_html = """        <section class="panel runtime-panel">
          <div class="panel-header runtime-header">
            <div class="runtime-header-title">
              <h2>实时运行</h2>
              <span id="nodeBadge" class="badge neutral">无节点</span>
            </div>
            <button id="toggleRuntimeBtn" class="button ghost" title="收起/展开">❯</button>
          </div>"""

if old_html in content:
    content = content.replace(old_html, new_html)
    # Re-apply the cache buster increment just in case
    content = content.replace("styles.css?v=4", "styles.css?v=5")
    content = content.replace("app.js?v=4", "app.js?v=5")
    with open("/Users/zhaoyu/Documents/agent-framework/app/web_static/index.html", "w") as f:
        f.write(content)
    print("HTML Patched!")
else:
    print("HTML block not found!")
