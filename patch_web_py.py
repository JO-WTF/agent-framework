import re

with open("/Users/zhaoyu/Documents/agent-framework/app/web.py", "r") as f:
    content = f.read()

broadcast_method = """    async def broadcast(self, event: dict[str, Any]) -> None:"""
new_broadcast_method = """    async def broadcast_stream(self, event: dict[str, Any]) -> None:
        stale = []
        for queue in self.subscribers:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                stale.append(queue)
        for queue in stale:
            self.subscribers.discard(queue)

    async def broadcast(self, event: dict[str, Any]) -> None:"""

content = content.replace(broadcast_method, new_broadcast_method)

old_update = """            last_event["title"] = f"节点更新: {active_node} (正在调用模型, {llm_run['token_count']} tokens)"
            last_event["updated_at"] = now
            await self.broadcast(last_event)"""

new_update = """            last_event["title"] = f"节点更新: {active_node} (正在调用模型, {llm_run['token_count']} tokens)"
            last_event["updated_at"] = now
            await self.broadcast_stream({"type": "stream", "content": token, "token_type": token_type})"""

content = content.replace(old_update, new_update)

with open("/Users/zhaoyu/Documents/agent-framework/app/web.py", "w") as f:
    f.write(content)

print("Patched web.py")
