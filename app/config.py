import os
import sys
import yaml
import httpx
from typing import Annotated, Any
from typing_extensions import NotRequired, TypedDict
from dotenv import load_dotenv
from tavily import TavilyClient
from langchain_openai import ChatOpenAI
from app.deepseek_chat import ChatDeepSeekReasoning
from langchain_core.callbacks import AsyncCallbackHandler
from langgraph.graph.message import add_messages
from app.runtime_paths import CONFIG_DIR
from app.llm_streaming import extract_thinking_and_content

# 加载外挂配置
load_dotenv()
with open(CONFIG_DIR / "prompts.yaml", "r", encoding="utf-8") as f:
    PROMPTS = yaml.safe_load(f)

# 定义 ReAct 状态流
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    revision_count: int
    eval_status: str
    session_id: NotRequired[str]  # Session identifier for data storage
    task_complexity: NotRequired[str]
    todo_list: NotRequired[list[dict[str, Any]]]
    context_tags: NotRequired[list[str]]
    active_skills: NotRequired[list[str]]
    world_state: NotRequired[dict[str, Any]]
    last_node: NotRequired[str]
    orchestrator_next: NotRequired[str]
    orchestrator_think: NotRequired[str]
    orchestrator_message: NotRequired[str]
    orchestrator_prompt: NotRequired[list[dict[str, str]]]
    evaluator_think: NotRequired[str]
    evaluator_message: NotRequired[str]
    evaluator_prompt: NotRequired[list[dict[str, str]]]


DEFAULT_PROVIDER_BASE_URLS = {
    "openai": "",
    "deepseek": "https://api.deepseek.com/v1",
    "ollama": "http://localhost:11434/v1",
    "llamacpp": "http://isc.ai.huawei.com:11434/v1",
}
DEFAULT_PROVIDER_MODEL_NAMES = {
    "openai": "gpt-4o-mini",
    "deepseek": "deepseek-v4-flash",
    "ollama": "qwen3",
    "llamacpp": "qwen3.6:latest",
}
_PROVIDER_API_KEY_ENVS = {
    "openai": "OPENAI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
}
_PROVIDER_FALLBACK_KEYS = {
    "ollama": "ollama",
    "llamacpp": "llamacpp",
}
_SUPPORTED_PROVIDERS = tuple(DEFAULT_PROVIDER_BASE_URLS.keys()) + ("custom",)


def _default_base_url(provider: str) -> str:
    return DEFAULT_PROVIDER_BASE_URLS.get(provider, "")


def _default_model_name(provider: str) -> str:
    return DEFAULT_PROVIDER_MODEL_NAMES.get(provider, "")


def _server_llm_settings() -> dict[str, Any]:
    provider = os.getenv("LLM_PROVIDER", "openai").lower()
    if provider not in _SUPPORTED_PROVIDERS:
        provider = "custom"
    return {
        "provider": provider,
        "model_name": os.getenv("LLM_MODEL_NAME") or _default_model_name(provider),
        "api_key": os.getenv("LLM_API_KEY") or "",
        "base_url": os.getenv("LLM_BASE_URL") or _default_base_url(provider),
        "temperature": float(os.getenv("LLM_TEMPERATURE", "0.1")),
    }


def _resolve_api_key(settings: dict[str, Any]) -> str:
    api_key = str(settings.get("api_key") or "")
    if api_key:
        return api_key
    provider = str(settings.get("provider") or "openai")
    env_name = _PROVIDER_API_KEY_ENVS.get(provider)
    if env_name:
        return os.getenv(env_name) or os.getenv("LLM_API_KEY") or "dummy"
    return _PROVIDER_FALLBACK_KEYS.get(provider, os.getenv("LLM_API_KEY") or "dummy")


def _has_configured_api_key(settings: dict[str, Any]) -> bool:
    provider = str(settings.get("provider") or "openai")
    env_name = _PROVIDER_API_KEY_ENVS.get(provider)
    return bool(settings.get("api_key") or os.getenv("LLM_API_KEY") or (env_name and os.getenv(env_name)))


def normalize_llm_settings(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Merge an optional browser-provided model config over server defaults."""
    current = _server_llm_settings()
    payload = payload or {}
    provider = str(payload.get("provider", current.get("provider", "openai"))).lower().strip()
    if provider not in _SUPPORTED_PROVIDERS:
        raise ValueError(f"Unsupported LLM provider: {provider}")

    current_provider = str(current.get("provider") or "openai")
    if "model_name" in payload:
        model_name_value = payload.get("model_name")
    elif provider != current_provider:
        model_name_value = _default_model_name(provider)
    else:
        model_name_value = current.get("model_name") or _default_model_name(provider)
    model_name = str(model_name_value or "").strip()
    if not model_name:
        raise ValueError("model_name is required")

    base_url = payload.get("base_url", current.get("base_url", ""))
    base_url = str(base_url or "").strip() or _default_base_url(provider)

    temperature_raw = payload.get("temperature", current.get("temperature", 0.1))
    try:
        temperature = float(temperature_raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("temperature must be a number") from exc

    api_key = current.get("api_key", "")
    if "api_key" in payload:
        api_key = str(payload.get("api_key") or "")

    return {
        "provider": provider,
        "model_name": model_name,
        "base_url": base_url,
        "api_key": api_key,
        "temperature": temperature,
    }


def redact_llm_settings(settings: dict[str, Any]) -> dict[str, Any]:
    redacted = dict(settings)
    redacted.pop("api_key", None)
    redacted["api_key_set"] = _has_configured_api_key(settings)
    redacted["providers"] = list(_SUPPORTED_PROVIDERS)
    redacted["default_base_urls"] = dict(DEFAULT_PROVIDER_BASE_URLS)
    redacted["default_model_names"] = dict(DEFAULT_PROVIDER_MODEL_NAMES)
    return redacted


def get_llm_settings() -> dict[str, Any]:
    """Return redacted server defaults for initializing the browser UI."""
    return redact_llm_settings(_server_llm_settings())


def _build_chat_openai(settings: dict[str, Any]) -> ChatOpenAI:
    model_name = str(settings.get("model_name") or "").strip()
    if not model_name:
        raise ValueError("LLM model name is required")

    base_url = str(settings.get("base_url") or "").strip()
    client_kwargs: dict[str, Any] = {
        "model": model_name,
        "temperature": float(settings.get("temperature", 0.1)),
        "streaming": True,
        "api_key": _resolve_api_key(settings),
        "http_client": httpx.Client(verify=False),
        "http_async_client": httpx.AsyncClient(verify=False),
    }
    if base_url:
        client_kwargs["base_url"] = base_url
    client_cls = ChatDeepSeekReasoning if settings.get("provider") == "deepseek" else ChatOpenAI
    return client_cls(**client_kwargs)


def get_llm_client(settings: dict[str, Any] | None = None) -> ChatOpenAI:
    return _build_chat_openai(normalize_llm_settings(settings))


def get_llm_client_from_config(config: Any = None) -> ChatOpenAI:
    configurable = (config or {}).get("configurable", {}) if isinstance(config, dict) else {}
    return get_llm_client(configurable.get("llm_settings"))


class RuntimeLLMClient:
    """Proxy that uses browser-provided settings from RunnableConfig when present."""

    def _client_from_call(self, args: tuple[Any, ...], kwargs: dict[str, Any]) -> ChatOpenAI:
        config = kwargs.get("config")
        if config is None and len(args) >= 2 and isinstance(args[1], dict):
            config = args[1]
        return get_llm_client_from_config(config)

    def __getattr__(self, name: str) -> Any:
        return getattr(get_llm_client(), name)

    def bind_tools(self, *args: Any, **kwargs: Any) -> Any:
        return get_llm_client().bind_tools(*args, **kwargs)

    async def ainvoke(self, *args: Any, **kwargs: Any) -> Any:
        return await self._client_from_call(args, kwargs).ainvoke(*args, **kwargs)

    def invoke(self, *args: Any, **kwargs: Any) -> Any:
        return self._client_from_call(args, kwargs).invoke(*args, **kwargs)

    def stream(self, *args: Any, **kwargs: Any) -> Any:
        return self._client_from_call(args, kwargs).stream(*args, **kwargs)

    def astream(self, *args: Any, **kwargs: Any) -> Any:
        return self._client_from_call(args, kwargs).astream(*args, **kwargs)


# 控制台绚丽日志回调
class StreamingConsoleCallback(AsyncCallbackHandler):
    async def on_llm_start(self, serialized, prompts, **kwargs):
        sys.stdout.write("\n🤖 \033[95m[思考中...]\033[0m ")
        sys.stdout.flush()
    async def on_llm_new_token(self, token: str, **kwargs) -> None:
        thinking, content = extract_thinking_and_content(kwargs.get("chunk"))
        if thinking:
            sys.stdout.write(f"\033[90m{thinking}\033[0m")
            sys.stdout.flush()

        text = content or token
        if text:
            sys.stdout.write(text)
            sys.stdout.flush()
    async def on_llm_end(self, response, **kwargs):
        sys.stdout.write("\n" + "-"*40 + "\n")
        sys.stdout.flush()


# 初始化底层大模型代理和搜索客户端
llm_client = RuntimeLLMClient()

search_client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))
