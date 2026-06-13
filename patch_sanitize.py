import re

with open("/Users/zhaoyu/Documents/agent-framework/app/memory/store.py", "r") as f:
    content = f.read()

sanitize_func = """def _sanitize_tool_messages(messages: list[Any]) -> list[Any]:
    sanitized = []
    pending_tool_calls: list[dict[str, Any]] = []
    
    for msg in messages:
        if isinstance(msg, (HumanMessage, AIMessage)) and pending_tool_calls:
            for tc in pending_tool_calls:
                sanitized.append(ToolMessage(
                    content="Tool execution was interrupted or cancelled. Continuing...",
                    tool_call_id=tc["id"],
                ))
            pending_tool_calls = []
            
        sanitized.append(msg)
        
        if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
            pending_tool_calls.extend(msg.tool_calls)
            
        if isinstance(msg, ToolMessage):
            pending_tool_calls = [tc for tc in pending_tool_calls if tc["id"] != getattr(msg, "tool_call_id", "")]
            
    if pending_tool_calls:
        for tc in pending_tool_calls:
            sanitized.append(ToolMessage(
                content="Tool execution was interrupted or cancelled. Continuing...",
                tool_call_id=tc["id"],
            ))
            
    return sanitized

def trim_messages(messages: list[Any], keep_recent: int = DEFAULT_MESSAGE_WINDOW, session_id: str | None = None) -> list[Any]:"""

content = content.replace("def trim_messages(messages: list[Any], keep_recent: int = DEFAULT_MESSAGE_WINDOW, session_id: str | None = None) -> list[Any]:", sanitize_func)

# Replace the two return statements in trim_messages
old_ret1 = "return _enforce_context_size([_build_summary_message(omitted)] + preserved + recent_messages, max_context_bytes, session_id)"
new_ret1 = "return _sanitize_tool_messages(_enforce_context_size([_build_summary_message(omitted)] + preserved + recent_messages, max_context_bytes, session_id))"

old_ret2 = "return _enforce_context_size(preserved + recent_messages, max_context_bytes, session_id)"
new_ret2 = "return _sanitize_tool_messages(_enforce_context_size(preserved + recent_messages, max_context_bytes, session_id))"

old_ret3 = "return _enforce_context_size(list(messages), max_context_bytes, session_id)"
new_ret3 = "return _sanitize_tool_messages(_enforce_context_size(list(messages), max_context_bytes, session_id))"

content = content.replace(old_ret1, new_ret1)
content = content.replace(old_ret2, new_ret2)
content = content.replace(old_ret3, new_ret3)

with open("/Users/zhaoyu/Documents/agent-framework/app/memory/store.py", "w") as f:
    f.write(content)

print("Patched trim_messages with sanitizer!")
