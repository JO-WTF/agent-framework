import os
import sys
import yaml
import httpx
from typing import Annotated, Any
from typing_extensions import NotRequired, TypedDict
from dotenv import load_dotenv
from tavily import TavilyClient
from langchain_openai import ChatOpenAI
from langchain_core.callbacks import AsyncCallbackHandler
from langgraph.graph.message import add_messages

# 加载外挂配置
load_dotenv()
with open("prompts.yaml", "r", encoding="utf-8") as f:
    PROMPTS = yaml.safe_load(f)

# 定义 ReAct 状态流
class AgentState(TypedDict):
    messages: Annotated[list, add_messages] 
    revision_count: int  
    eval_status: str
    task_complexity: NotRequired[str]
    todo_list: NotRequired[list[dict[str, Any]]]
    orchestrator_next: NotRequired[str]

# 控制台绚丽日志回调
class StreamingConsoleCallback(AsyncCallbackHandler):
    async def on_llm_start(self, serialized, prompts, **kwargs):
        sys.stdout.write("\n🤖 \033[95m[思考中...]\033[0m ")
        sys.stdout.flush()
    async def on_llm_new_token(self, token: str, **kwargs) -> None:
        if token:
            sys.stdout.write(token)
            sys.stdout.flush()
    async def on_llm_end(self, response, **kwargs):
        sys.stdout.write("\n" + "-"*40 + "\n")
        sys.stdout.flush()

def get_llm_client():
    provider = os.getenv("LLM_PROVIDER", "openai").lower()
    model_name = os.getenv("LLM_MODEL_NAME")
    api_key = os.getenv("LLM_API_KEY")
    base_url = os.getenv("LLM_BASE_URL")
    temperature = float(os.getenv("LLM_TEMPERATURE", "0.1"))
    
    # 绝大部分现代接口（包括 DeepSeek, Ollama, llama.cpp）都兼容 OpenAI API 格式
    # 因此我们可以统一使用 ChatOpenAI，只需根据服务商调整参数
    client_kwargs = {
        "model": model_name,
        "temperature": temperature,
        "streaming": True,
        "http_client": httpx.Client(verify=False),
        "http_async_client": httpx.AsyncClient(verify=False)
    }

    if provider == "openai":
        client_kwargs["api_key"] = api_key or os.getenv("OPENAI_API_KEY")
        if base_url:
            client_kwargs["base_url"] = base_url
    elif provider == "deepseek":
        client_kwargs["api_key"] = api_key or os.getenv("DEEPSEEK_API_KEY", "dummy")
        client_kwargs["base_url"] = base_url or "https://api.deepseek.com/v1"
    elif provider == "ollama":
        # Ollama 原生支持 OpenAI 兼容 API，通常运行在 11434 端口
        client_kwargs["api_key"] = api_key or "ollama"
        client_kwargs["base_url"] = base_url or "http://localhost:11434/v1"
    elif provider == "llamacpp":
        # llama.cpp server 同样提供 OpenAI 兼容 API
        client_kwargs["api_key"] = api_key or "llamacpp"
        client_kwargs["base_url"] = base_url or "http://localhost:8080/v1"
    else:
        # 默认回退
        client_kwargs["api_key"] = api_key or "dummy"
        if base_url:
            client_kwargs["base_url"] = base_url

    return ChatOpenAI(**client_kwargs)

# 初始化底层大模型和搜索客户端
llm_client = get_llm_client()

search_client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))
