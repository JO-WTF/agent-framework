import re

with open("/Users/zhaoyu/Documents/agent-framework/app/web_static/app.js", "r") as f:
    content = f.read()

old_listener = """els.eventList.addEventListener("click", (event) => {
  const button = event.target.closest(".event-detail-button");
  if (!button) return;
  const eventId = button.dataset.eventId;
  if (!eventId) return;
  if (expandedEvents.has(eventId)) {
    expandedEvents.delete(eventId);
  } else {
    expandedEvents.add(eventId);
  }
  loadState();
});"""

new_listener = """els.eventList.addEventListener("click", (event) => {
  const button = event.target.closest(".event-detail-button");
  if (!button) return;
  const eventId = button.dataset.eventId;
  if (!eventId) return;
  if (expandedEvents.has(eventId)) {
    expandedEvents.delete(eventId);
  } else {
    expandedEvents.add(eventId);
  }
  renderEvents(currentState.events || []);
});"""

content = content.replace(old_listener, new_listener)

with open("/Users/zhaoyu/Documents/agent-framework/app/web_static/app.js", "w") as f:
    f.write(content)

print("Applied event listener patch")
