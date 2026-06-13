with open("/Users/zhaoyu/Documents/agent-framework/app/web_static/app.js", "r") as f:
    content = f.read()

old_func = """function renderState(state) {
  currentState = { ...currentState, ...(state || {}) };
  state = currentState;"""

new_func = """let renderStateRafId = null;

function renderState(state) {
  currentState = { ...currentState, ...(state || {}) };
  
  if (renderStateRafId) return;
  
  renderStateRafId = requestAnimationFrame(() => {
    renderStateRafId = null;
    const state = currentState;"""

if old_func in content:
    content = content.replace(old_func, new_func)
    
    # Need to add a closing brace to renderState
    # Let's find the end of renderState
    # It ends with renderRoutes(state);\n}
    content = content.replace("  renderRoutes(state);\n}", "  renderRoutes(state);\n  });\n}")
    
    # Increment cache buster
    content = content.replace("app.js?v=7", "app.js?v=8")
    content = content.replace("styles.css?v=7", "styles.css?v=8")
    
    with open("/Users/zhaoyu/Documents/agent-framework/app/web_static/app.js", "w") as f:
        f.write(content)
    print("Patched renderState with requestAnimationFrame!")
else:
    print("Could not find renderState block")
