from __future__ import annotations

import asyncio
import json
import re
from html import unescape
from html.parser import HTMLParser
from typing import Any

import httpx
from langchain_core.runnables.config import RunnableConfig
from langchain_core.tools import tool

from app.config import PROMPTS
from app.logging_config import logger
from app.memory.store import summarize_text
from app.tools.context import get_session_id_from_config_or_context
from app.tools.storage import store_tool_result_for_current_session

DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_MAX_CHARS = 2400
MAX_RETURN_CHARS = 6000
MAX_STORED_CHARS = 200_000
SKIP_TAGS = {"script", "style", "code", "pre", "nav", "footer", "header", "svg", "canvas", "noscript"}
BLOCK_TAGS = {"p", "div", "section", "article", "main", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"}
HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}


def _strip_code_and_noise(html: str) -> str:
    cleaned = html
    for tag in SKIP_TAGS:
        cleaned = re.sub(rf"<{tag}\b[^>]*>.*?</{tag}>", " ", cleaned, flags=re.I | re.S)
    cleaned = re.sub(r"<!--.*?-->", " ", cleaned, flags=re.S)
    return cleaned


def _normalize_text(text: str) -> str:
    text = unescape(text)
    text = text.replace("\xa0", " ")
    lines = []
    seen: set[str] = set()
    for raw_line in text.splitlines():
        line = re.sub(r"[ \t]+", " ", raw_line).strip()
        if not line:
            continue
        dedupe_key = line.lower()
        if len(line) > 40 and dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        lines.append(line)
    return "\n".join(lines).strip()


class _ReadableTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.skip_depth = 0
        self.title_parts: list[str] = []
        self.description = ""
        self.current_tag = ""
        self.parts: list[str] = []
        self.headings: list[str] = []
        self._in_title = False
        self._current_heading: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        self.current_tag = tag
        if tag in SKIP_TAGS:
            self.skip_depth += 1
            return
        if tag == "title":
            self._in_title = True
        if tag == "meta":
            attr_map = {name.lower(): value or "" for name, value in attrs}
            name = attr_map.get("name", "").lower()
            prop = attr_map.get("property", "").lower()
            if name == "description" or prop == "og:description":
                self.description = attr_map.get("content", self.description).strip()
        if tag in HEADING_TAGS:
            self._current_heading = []
        if tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in SKIP_TAGS and self.skip_depth:
            self.skip_depth -= 1
            return
        if tag == "title":
            self._in_title = False
        if tag in HEADING_TAGS and self._current_heading is not None:
            heading = _normalize_text(" ".join(self._current_heading))
            if heading:
                self.headings.append(heading)
            self._current_heading = None
        if tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self.skip_depth:
            return
        text = data.strip()
        if not text:
            return
        if self._in_title:
            self.title_parts.append(text)
            return
        if self._current_heading is not None:
            self._current_heading.append(text)
        self.parts.append(text)
        self.parts.append(" ")

    def result(self) -> dict[str, Any]:
        return {
            "title": _normalize_text(" ".join(self.title_parts)),
            "description": _normalize_text(self.description),
            "headings": self.headings[:20],
            "text": _normalize_text("".join(self.parts)),
            "extractor": "html_parser_fallback",
        }


def _fallback_extract(html: str) -> dict[str, Any]:
    parser = _ReadableTextParser()
    parser.feed(_strip_code_and_noise(html))
    return parser.result()


def extract_readable_webpage(html: str, *, url: str = "", include_tables: bool = False) -> dict[str, Any]:
    cleaned_html = _strip_code_and_noise(html)
    fallback = _fallback_extract(cleaned_html)
    try:
        import trafilatura
        from trafilatura.metadata import extract_metadata

        text = trafilatura.extract(
            cleaned_html,
            url=url or None,
            output_format="markdown",
            include_comments=False,
            include_tables=include_tables,
            include_links=False,
            favor_precision=True,
        )
        metadata = extract_metadata(cleaned_html, default_url=url or None)
        if text:
            return {
                "title": fallback.get("title") or getattr(metadata, "title", "") or "",
                "description": fallback.get("description") or getattr(metadata, "description", "") or "",
                "author": getattr(metadata, "author", "") or "",
                "date": getattr(metadata, "date", "") or "",
                "sitename": getattr(metadata, "sitename", "") or "",
                "headings": fallback.get("headings", []),
                "text": _normalize_text(text),
                "extractor": "trafilatura",
            }
    except Exception:
        pass
    return fallback


async def _fetch_html(url: str, headers: dict[str, str] | None = None) -> tuple[int, dict[str, str], str]:
    request_headers = {
        "User-Agent": "AgentFramework/1.0 (+read_webpage)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,text/plain;q=0.8,*/*;q=0.5",
    }
    if headers:
        request_headers.update(headers)
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_SECONDS, follow_redirects=True, verify=False) as client:
        response = await client.get(url, headers=request_headers)
    return response.status_code, dict(response.headers), response.text


def _build_stored_payload(url: str, status_code: int, headers: dict[str, str], extracted: dict[str, Any]) -> str:
    payload = {
        "url": url,
        "status_code": status_code,
        "content_type": headers.get("content-type", ""),
        "extractor": extracted.get("extractor", ""),
        "title": extracted.get("title", ""),
        "description": extracted.get("description", ""),
        "author": extracted.get("author", ""),
        "date": extracted.get("date", ""),
        "sitename": extracted.get("sitename", ""),
        "headings": extracted.get("headings", []),
        "text": summarize_text(str(extracted.get("text", "")), max_chars=MAX_STORED_CHARS),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


@tool(description=PROMPTS["tools"]["read_webpage"])
async def read_webpage(
    url: str,
    max_chars: int = DEFAULT_MAX_CHARS,
    include_tables: bool = False,
    headers: dict[str, str] | None = None,
    config: RunnableConfig = None,
) -> str:
    get_session_id_from_config_or_context(config)
    logger.info(f"📖 \033[94m[触发工具: 网页正文提取] -> {url}\033[0m")

    safe_url = str(url or "").strip()
    if not safe_url.startswith(("http://", "https://")):
        text = "错误: read_webpage 只支持 http:// 或 https:// URL。"
        store_tool_result_for_current_session("read_webpage", text, {"url": safe_url, "status": "invalid_url"})
        return text

    try:
        status_code, response_headers, html = await _fetch_html(safe_url, headers=headers)
        extracted = await asyncio.to_thread(extract_readable_webpage, html, url=safe_url, include_tables=include_tables)
    except Exception as exc:
        text = f"网页读取失败: {str(exc)}"
        store_tool_result_for_current_session("read_webpage", text, {"url": safe_url, "status": "error"})
        return text

    full_text = str(extracted.get("text") or "")
    stored_payload = _build_stored_payload(safe_url, status_code, response_headers, extracted)
    ref_id = store_tool_result_for_current_session(
        "read_webpage",
        stored_payload,
        {
            "url": safe_url,
            "status_code": status_code,
            "content_type": response_headers.get("content-type", ""),
            "extractor": extracted.get("extractor", ""),
            "text_length": len(full_text),
        },
    )

    safe_max_chars = max(500, min(int(max_chars), MAX_RETURN_CHARS))
    preview = summarize_text(full_text, max_chars=safe_max_chars)
    title = extracted.get("title") or "(未提取到标题)"
    description = extracted.get("description") or ""
    headings = extracted.get("headings") or []
    heading_text = "\n".join(f"- {heading}" for heading in headings[:8])

    return "\n".join(
        part
        for part in [
            f"状态码: {status_code}",
            f"标题: {title}",
            f"描述: {description}" if description else "",
            f"提取器: {extracted.get('extractor', 'unknown')}",
            f"正文长度: {len(full_text)} 字符；完整提取结果已保存为引用 {ref_id}。",
            f"主要标题:\n{heading_text}" if heading_text else "",
            f"正文预览:\n{preview}" if preview else "正文预览: (未提取到正文)",
            f"如需更多内容，请调用 read_tool_result(ref_id=\"{ref_id}\") 分页读取。",
        ]
        if part
    )
