import json
from langchain_core.tools import tool
from langchain_core.runnables.config import RunnableConfig

from app.config import PROMPTS
from app.logging_config import logger
from app.memory.store import save_agent_note, summarize_text
from app.tools.context import get_session_id_from_config_or_context
from app.tools.storage import store_tool_result_for_current_session
from app.tools.sandbox import run_sandboxed_python

HTML_CONTENT_TYPES = ("text/html", "application/xhtml+xml")
HTML_BODY_PATTERNS = ("<html", "<!doctype html", "<body", "<head")


def _is_html_response(headers: dict[str, str], text: str) -> bool:
    content_type = ""
    for key, value in headers.items():
        if key.lower() == "content-type":
            content_type = str(value).lower()
            break
    if any(kind in content_type for kind in HTML_CONTENT_TYPES):
        return True
    sample = text[:2048].lower()
    return any(pattern in sample for pattern in HTML_BODY_PATTERNS)


@tool(description=PROMPTS["tools"]["api_request"])
async def api_request(
    url: str,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    data: str | None = None,
    config: RunnableConfig = None,
) -> str:
    get_session_id_from_config_or_context(config)
    logger.info(f"🌐 \033[94m[触发工具: API Request] -> {method} {url}\033[0m")

    # Normalize method
    method_upper = method.strip().upper()
    valid_methods = {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"}
    if method_upper not in valid_methods:
        text = f"错误: 不支持的 HTTP 方法 '{method}'。"
        store_tool_result_for_current_session("api_request", text, {"url": url, "method": method, "status": "invalid_method"})
        return text

    # Execute inside the Docker sandbox
    logger.info("📦 [api_request] 正在沙箱环境内发起请求...")
    
    # We construct a clean python script to run inside the sandbox container
    py_code = (
        "import requests\n"
        "import json\n"
        "\n"
        f"url = {repr(url)}\n"
        f"method = {repr(method_upper)}\n"
        f"headers = {repr(headers)}\n"
        f"data = {repr(data)}\n"
        "\n"
        "req_kwargs = {}\n"
        "if headers:\n"
        "    req_kwargs['headers'] = headers\n"
        "if data:\n"
        "    try:\n"
        "        req_kwargs['json'] = json.loads(data)\n"
        "    except ValueError:\n"
        "        req_kwargs['data'] = data.encode('utf-8')\n"
        "\n"
        "try:\n"
        "    response = requests.request(method, url, timeout=30.0, **req_kwargs)\n"
        "    result = {\n"
        "        'status_code': response.status_code,\n"
        "        'text': response.text,\n"
        "        'headers': dict(response.headers),\n"
        "        'success': True\n"
        "    }\n"
        "except Exception as e:\n"
        "    result = {\n"
        "        'success': False,\n"
        "        'error': str(e)\n"
        "    }\n"
        "print(json.dumps(result))\n"
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
            raise RuntimeError(result_obj.stderr or "沙箱 HTTP 请求未返回结果")
        response_data = json.loads(stdout)
        if not response_data.get("success"):
            raise RuntimeError(response_data.get("error", "未知请求错误"))

        status_code = response_data["status_code"]
        response_text = response_data["text"]
        response_headers = response_data["headers"]

    except Exception as e:
        error_msg = f"沙箱内 HTTP 请求失败: {str(e)}"
        store_tool_result_for_current_session("api_request", error_msg, {"url": url, "method": method_upper, "status": "error"})
        note_id = save_agent_note(f"api_request 沙箱请求失败：{method_upper} {url}\n错误: {str(e)}", source="api_request", tags=["api_call", "tool_error"])
        return f"请求失败: {str(e)}。已记录笔记 {note_id}。"

    if method_upper == "GET" and _is_html_response(response_headers, response_text):
        text = (
            "错误: api_request 禁止用于获取网页 HTML 主体内容。"
            "如需阅读网页正文、文章、文档或页面摘要，请改用 read_webpage(url=...)。"
            "api_request 仅用于 API/JSON、非 HTML 资源、请求调试或需要原始协议响应的场景。"
        )
        store_tool_result_for_current_session(
            "api_request",
            text,
            {
                "url": url,
                "method": method_upper,
                "status_code": status_code,
                "headers": response_headers,
                "status": "html_blocked_use_read_webpage",
            },
        )
        return text

    # Common response archiving logic
    ref_id = store_tool_result_for_current_session(
        "api_request",
        response_text,
        {
            "url": url,
            "method": method_upper,
            "status_code": status_code,
            "headers": response_headers,
        },
    )

    if len(response_text) > 1024:
        summary = summarize_text(response_text, max_chars=512)
        return (
            f"状态码: {status_code}\n"
            f"API 响应内容过长，已保存为引用 {ref_id}。\n"
            f"如需完整内容，请调用 read_tool_result(ref_id=\"{ref_id}\")。\n"
            f"摘要:\n{summary}"
        )

    return f"状态码: {status_code}\n响应内容:\n{response_text}"
