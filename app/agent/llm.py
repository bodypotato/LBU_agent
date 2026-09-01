"""LLM 工厂：根据 .env 构建 create_agent 所需的 model。"""

from functools import lru_cache

from langchain_ollama import ChatOllama

from app.config import get_settings


@lru_cache
def get_llm() -> ChatOllama:
    """构建 ChatOllama 实例。

    .env 中的 OLLAMA_MODEL / OLLAMA_BASE_URL 即 create_agent 的 model 参数来源；
    qwen3 支持 tool calling 与 thinking，agent 的工具调用与推理均可用。
    """
    settings = get_settings()
    return ChatOllama(
        model=settings.ollama_model,
        base_url=settings.ollama_native_url,
        temperature=settings.agent_temperature,
        timeout=settings.agent_timeout,
    )
