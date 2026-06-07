from langgraph.prebuilt import ToolNode

from app.config import AgentState
from app.tools.registry import AGENT_TOOLS
from app.tools.context import set_session_id


_base_tools_execution_node = ToolNode(AGENT_TOOLS)


async def tools_execution_node(state: AgentState):
    session_id = state.get("session_id", "cli")
    set_session_id(session_id)
    return await _base_tools_execution_node.ainvoke(state)
