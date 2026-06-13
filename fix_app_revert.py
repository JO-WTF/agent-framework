import re

with open("/Users/zhaoyu/Documents/agent-framework/app/web_static/app.js", "r") as f:
    content = f.read()

# 1. Update `els`
old_els = """const els = {
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
};"""

new_els = """const els = {
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
  eventList: document.getElementById("eventList"),
  todoList: document.getElementById("todoList"),
  approvalList: document.getElementById("approvalList"),
  routeList: document.getElementById("routeList"),
  progressSplit: document.getElementById("progressSplit"),
  progressResizeHandle: document.getElementById("progressResizeHandle"),
  complexityValue: document.getElementById("complexityValue"),
  currentNodeValue: document.getElementById("currentNodeValue"),
  workspace: document.querySelector(".workspace"),
  toggleRuntimeBtn: document.getElementById("toggleRuntimeBtn"),
};"""

if "els.workspace" not in content:
    content = content.replace(old_els, new_els)

# 2. Add toggleRuntimeBtn listener at the bottom
drawer_logic = """
if (els.toggleRuntimeBtn) {
  els.toggleRuntimeBtn.addEventListener("click", () => {
    els.workspace.classList.toggle("runtime-collapsed");
    setTimeout(() => window.dispatchEvent(new Event('resize')), 300);
  });
}
"""
if "els.toggleRuntimeBtn.addEventListener" not in content:
    content = content.replace("connectWs();", drawer_logic + "\nconnectWs();")

# 3. Remove `modelOutput` rendering from `renderState`
old_render_state_inner = """  els.modelOutput.innerHTML = renderModelOutput(state.model_output || "");
  els.modelOutput.scrollTop = els.modelOutput.scrollHeight;"""

content = content.replace(old_render_state_inner, "")

with open("/Users/zhaoyu/Documents/agent-framework/app/web_static/app.js", "w") as f:
    f.write(content)

print("Applied drawer fix and removed modelOutput crash!")
