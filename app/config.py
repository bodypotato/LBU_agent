"""配置层：从 .env 读取全部运行参数。

create_agent 所需的 LLM 参数（model / base_url）与 agent 行为参数均在此集中管理，
后续新增的 LinkBetweenUs 对接参数（如后端地址、JWT 密钥等）也统一放这里。
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """全局配置，字段与 .env 一一对应。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---- create_agent / LLM 参数 ----
    ollama_model: str = "qwen3:4b"
    ollama_base_url: str = "http://localhost:11434/v1"

    # ---- Agent 行为 ----
    agent_name: str = "LBU 助手"
    agent_temperature: float = 0.7
    agent_timeout: int = 120  # LLM 单次请求超时（秒）

    # ---- LinkBetweenUs 后端（供工具对接）----
    lbu_backend_base_url: str = "http://localhost:8080"

    @property
    def ollama_native_url(self) -> str:
        """Ollama 原生 API 地址。

        .env 中约定的是 OpenAI 兼容格式（带 /v1），而 langchain-ollama 的
        ChatOllama 走 Ollama 原生协议，这里统一剥掉 /v1 后缀。
        """
        url = self.ollama_base_url.rstrip("/")
        return url.removesuffix("/v1")


@lru_cache
def get_settings() -> Settings:
    return Settings()
