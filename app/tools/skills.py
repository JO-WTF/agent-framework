import re
import yaml
from langchain_core.tools import tool
from langchain_core.runnables.config import RunnableConfig

from app.config import PROMPTS
from app.logging_config import logger
from app.memory.store import SKILLS_DIR, normalize_context_tags
from app.tools.context import get_session_id_from_config_or_context
from app.tools.storage import store_tool_result_for_current_session


@tool(description=PROMPTS["tools"]["save_skill_sop"])
async def save_skill_sop(name: str, description: str, tags: list[str], instructions: str, config: RunnableConfig = None) -> str:
    get_session_id_from_config_or_context(config)
    logger.info(f"🛠️ \033[94m[触发工具: 保存技能 SOP] -> {name}\033[0m")

    # Validate name to prevent directory traversal
    if not re.match(r"^[a-zA-Z0-9_-]+$", name):
        text = f"错误: 技能名称 '{name}' 不合法。只允许使用字母、数字、下划线和连字符。"
        store_tool_result_for_current_session("save_skill_sop", text, {"name": name, "status": "error"})
        return text

    try:
        SKILLS_DIR.mkdir(parents=True, exist_ok=True)
        file_path = SKILLS_DIR / f"{name}.md"

        # Clean tags
        cleaned_tags = normalize_context_tags(tags)

        # Build YAML frontmatter and content
        frontmatter = {
            "name": name,
            "description": description,
            "tags": cleaned_tags
        }

        # Format yaml
        frontmatter_yaml = yaml.dump(frontmatter, allow_unicode=True, sort_keys=False).strip()

        file_content = f"---\n{frontmatter_yaml}\n---\n\n{instructions.strip()}\n"

        file_path.write_text(file_content, encoding="utf-8")

        text = f"成功: 技能 SOP '{name}' 已保存至 {file_path}，标签: {cleaned_tags}。"
        store_tool_result_for_current_session("save_skill_sop", text, {"name": name, "tags": cleaned_tags, "status": "success"})
        return text
    except Exception as e:
        text = f"保存技能 SOP 失败: {str(e)}"
        store_tool_result_for_current_session("save_skill_sop", text, {"name": name, "status": "error"})
        return text


@tool(description=PROMPTS["tools"]["list_skills"])
async def list_skills(config: RunnableConfig = None) -> str:
    get_session_id_from_config_or_context(config)
    logger.info("🛠️ \033[94m[触发工具: 列出所有技能 SOP]\033[0m")

    if not SKILLS_DIR.exists() or not SKILLS_DIR.is_dir():
        text = "暂无可用技能 SOP。"
        store_tool_result_for_current_session("list_skills", text, {"count": 0})
        return text

    skills = []
    for path in sorted(SKILLS_DIR.glob("*.md")):
        try:
            content = path.read_text(encoding="utf-8")
            if not content.startswith("---"):
                continue
            parts = content.split("---", 2)
            if len(parts) < 3:
                continue
            frontmatter_raw = parts[1]
            meta = yaml.safe_load(frontmatter_raw) or {}
            skills.append({
                "name": meta.get("name") or path.stem,
                "description": meta.get("description") or "",
                "tags": meta.get("tags") or []
            })
        except Exception:
            pass

    if not skills:
        text = "暂无可用技能 SOP。"
        store_tool_result_for_current_session("list_skills", text, {"count": 0})
        return text

    lines = ["可用技能 SOP 列表:"]
    for s in skills:
        lines.append(f"- **{s['name']}**: {s['description']} (标签: {s['tags']})")

    text = "\n".join(lines)
    store_tool_result_for_current_session("list_skills", text, {"count": len(skills)})
    return text


@tool(description=PROMPTS["tools"]["delete_skill_sop"])
async def delete_skill_sop(name: str, config: RunnableConfig = None) -> str:
    get_session_id_from_config_or_context(config)
    logger.info(f"🛠️ \033[94m[触发工具: 删除技能 SOP] -> {name}\033[0m")

    # Validate name to prevent directory traversal
    if not re.match(r"^[a-zA-Z0-9_-]+$", name):
        text = f"错误: 技能名称 '{name}' 不合法。只允许使用字母、数字、下划线和连字符。"
        store_tool_result_for_current_session("delete_skill_sop", text, {"name": name, "status": "error"})
        return text

    try:
        file_path = SKILLS_DIR / f"{name}.md"
        if not file_path.exists():
            text = f"错误: 技能 SOP '{name}' 不存在。"
            store_tool_result_for_current_session("delete_skill_sop", text, {"name": name, "status": "not_found"})
            return text

        file_path.unlink()
        text = f"成功: 技能 SOP '{name}' 已删除。"
        store_tool_result_for_current_session("delete_skill_sop", text, {"name": name, "status": "success"})
        return text
    except Exception as e:
        text = f"删除技能 SOP 失败: {str(e)}"
        store_tool_result_for_current_session("delete_skill_sop", text, {"name": name, "status": "error"})
        return text


@tool(description=PROMPTS["tools"]["get_skill_sop"])
async def get_skill_sop(name: str, config: RunnableConfig = None) -> str:
    get_session_id_from_config_or_context(config)
    logger.info(f"🛠️ \033[94m[触发工具: 查看技能详情 SOP] -> {name}\033[0m")

    # Validate name to prevent directory traversal
    if not re.match(r"^[a-zA-Z0-9_-]+$", name):
        text = f"错误: 技能名称 '{name}' 不合法。只允许使用字母、数字、下划线和连字符。"
        store_tool_result_for_current_session("get_skill_sop", text, {"name": name, "status": "error"})
        return text

    try:
        file_path = SKILLS_DIR / f"{name}.md"
        if not file_path.exists():
            text = f"错误: 技能 SOP '{name}' 不存在。"
            store_tool_result_for_current_session("get_skill_sop", text, {"name": name, "status": "not_found"})
            return text

        content = file_path.read_text(encoding="utf-8")
        store_tool_result_for_current_session("get_skill_sop", content, {"name": name, "status": "success"})
        return content
    except Exception as e:
        text = f"读取技能 SOP 失败: {str(e)}"
        store_tool_result_for_current_session("get_skill_sop", text, {"name": name, "status": "error"})
        return text


