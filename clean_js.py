with open("/Users/zhaoyu/Documents/agent-framework/app/web_static/app.js", "r") as f:
    content = f.read()

# Find the start of the injected code
# The injection starts with: // Force inject button if it doesn't exist
idx = content.find("// Force inject button if it doesn't exist")

if idx != -1:
    clean_content = content[:idx] + """els.toggleRuntimeBtn.addEventListener("click", () => {
  els.workspace.classList.toggle("runtime-collapsed");
  // Trigger map resize if map widget exists, to adapt to new chat panel width
  setTimeout(() => {
    window.dispatchEvent(new Event('resize'));
  }, 300);
});
"""
    with open("/Users/zhaoyu/Documents/agent-framework/app/web_static/app.js", "w") as f:
        f.write(clean_content)
    print("Cleaned!")
else:
    print("Not found")
