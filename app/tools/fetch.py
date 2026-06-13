import json

from langchain_core.runnables.config import RunnableConfig
from langchain_core.tools import tool

from app.config import PROMPTS
from app.logging_config import logger
from app.memory.store import save_agent_note, summarize_text
from app.tools.context import get_session_id_from_config_or_context
from app.tools.sandbox import run_sandboxed_python
from app.tools.storage import store_tool_result_for_current_session


@tool(description=PROMPTS["tools"]["fetch_url"])
async def fetch_url(url: str, max_chars: int = 12000, config: RunnableConfig = None) -> str:
    get_session_id_from_config_or_context(config)
    logger.info(f"🌐 \033[94m[触发工具: 获取网页正文] -> {url}\033[0m")
    safe_limit = max(1000, min(int(max_chars), 50000))
    py_code = (
        "import html\n"
        "import json\n"
        "import re\n"
        "import requests\n"
        f"url = {url!r}\n"
        f"max_chars = {safe_limit!r}\n"
        "try:\n"
        "    response = requests.get(url, timeout=30.0, headers={'User-Agent': 'agent-framework/1.0'})\n"
        "    content_type = response.headers.get('content-type', '')\n"
        "    text = response.text\n"
        "    title = ''\n"
        "    if 'html' in content_type.lower() or '<html' in text[:500].lower():\n"
        "        title_match = re.search(r'<title[^>]*>(.*?)</title>', text, flags=re.I | re.S)\n"
        "        if title_match:\n"
        "            title = html.unescape(re.sub(r'\\s+', ' ', title_match.group(1))).strip()\n"
        "        text = re.sub(r'<(script|style|noscript)[^>]*>.*?</\\1>', ' ', text, flags=re.I | re.S)\n"
        "        text = re.sub(r'<[^>]+>', ' ', text)\n"
        "        text = html.unescape(text)\n"
        "    text = re.sub(r'\\s+', ' ', text).strip()\n"
        "    result = {\n"
        "        'success': True,\n"
        "        'url': response.url,\n"
        "        'status_code': response.status_code,\n"
        "        'content_type': content_type,\n"
        "        'title': title,\n"
        "        'text': text[:max_chars],\n"
        "        'content_length': len(text),\n"
        "        'truncated': len(text) > max_chars,\n"
        "    }\n"
        "except Exception as e:\n"
        "    result = {'success': False, 'error': str(e)}\n"
        "print(json.dumps(result, ensure_ascii=False))\n"
    )
    try:
        import asyncio
        import contextvars

        loop = asyncio.get_event_loop()
        ctx = contextvars.copy_context()
        result_obj = await loop.run_in_executor(None, lambda: ctx.run(run_sandboxed_python, py_code))
        if result_obj.returncode != 0:
            raise RuntimeError(result_obj.stderr or "沙箱 Python 解释器执行异常")
        stdout = result_obj.stdout.strip()
        if not stdout:
            raise RuntimeError(result_obj.stderr or "沙箱网页抓取未返回结果")
        payload = json.loads(stdout)
        if not payload.get("success"):
            raise RuntimeError(payload.get("error", "未知抓取错误"))
    except Exception as e:
        error_msg = f"网页抓取失败: {str(e)}"
        store_tool_result_for_current_session("fetch_url", error_msg, {"url": url, "status": "error"})
        note_id = save_agent_note(f"fetch_url 失败：{url}\n错误: {str(e)}", source="fetch_url", tags=["web", "tool_error"])
        return f"抓取失败: {str(e)}。已记录笔记 {note_id}。"

    text = str(payload.get("text", ""))
    result_text = (
        f"URL: {payload.get('url', url)}\n"
        f"状态码: {payload.get('status_code')}\n"
        f"Content-Type: {payload.get('content_type', '')}\n"
        f"标题: {payload.get('title', '')}\n"
        f"正文长度: {payload.get('content_length', len(text))} truncated={str(payload.get('truncated', False)).lower()}\n\n"
        f"{text}"
    )
    ref_id = store_tool_result_for_current_session(
        "fetch_url",
        result_text,
        {
            "url": url,
            "resolved_url": payload.get("url", url),
            "status_code": payload.get("status_code"),
            "content_type": payload.get("content_type", ""),
            "truncated": payload.get("truncated", False),
        },
    )
    if len(result_text) > 2048:
        summary = summarize_text(result_text, max_chars=800)
        return (
            f"网页正文较长，已保存为引用 {ref_id}。\n"
            f"如需完整内容，请调用 read_tool_result(ref_id=\"{ref_id}\")，必要时使用 offset/limit 分页。\n"
            f"摘要:\n{summary}"
        )
    return result_text
