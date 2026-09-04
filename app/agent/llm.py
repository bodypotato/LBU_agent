"""LLM 工厂：根据 .env 构建 create_agent 所需的 model。"""

from functools import lru_cache

from langchain_ollama import ChatOllama

from app.config import get_settings


@lru_cache
def get_llm() -> ChatOllama:
    """构建 ChatOllama 实例（进程内单例，lru_cache 保证服务生命周期内只创建一次）。

    .env 中的 OLLAMA_MODEL / OLLAMA_BASE_URL 即 create_agent 的 model 参数来源；
    qwen3 支持 tool calling 与 thinking，agent 的工具调用与推理均可用。
    """
    settings = get_settings()
    return ChatOllama(
        model=settings.ollama_model,
        base_url=settings.ollama_native_url,
        temperature=settings.agent_temperature,
        timeout=settings.agent_timeout,
        # Ollama 运行时默认 num_ctx 仅 4096，工具定义较多时会被截断，
        # 这里显式按 .env 的 OLLAMA_NUM_CTX 设置（qwen3 支持到 26 万）
        num_ctx=settings.ollama_num_ctx,
    )
