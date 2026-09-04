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

    # ---- Redis（会话 checkpointer 持久化）----
    redis_url: str = "http://localhost:6379"
    redis_password: str = ""

    # ---- MySQL（历史对话存储，仅展示用，不参与上下文）----
    mysql_host: str = "localhost"
    mysql_port: int = 3306
    mysql_database: str = "Link_Between_Us"
    mysql_user: str = "root"
    mysql_password: str = ""

    # ---- RAG（LBU 产品文档检索增强）----
    embedding_model_name: str = "Qwen/Qwen3-Embedding-0.6B"
    embedding_device: str = "cpu"
    chroma_persist_dir: str = "./chroma_db"
    rag_doc_dir: str = "docs"  # 全部 .md 均为文档源，按文件增量建索引
    rag_top_k: int = 4

    # ---- 上下文裁剪（超长对话自动压缩，SummarizationMiddleware）----
    summary_trigger_messages: int = 20  # 消息数达到该值触发压缩
    summary_keep_messages: int = 4  # 压缩后保留的最新消息数

    # ---- 文件工具（agent 专属工作区）----
    agent_workspace_dir: str = "workspace"  # 文件工具读写根目录（相对进程工作目录）
    file_max_read_chars: int = 8000  # read_file 单次返回的字符上限

    @property
    def ollama_native_url(self) -> str:
        """Ollama 原生 API 地址。

        .env 中约定的是 OpenAI 兼容格式（带 /v1），而 langchain-ollama 的
        ChatOllama 走 Ollama 原生协议，这里统一剥掉 /v1 后缀。
        """
        url = self.ollama_base_url.rstrip("/")
        return url.removesuffix("/v1")

    @property
    def redis_dsn(self) -> str:
        """构造 redis-py / RedisSaver 使用的标准 DSN。

        .env 中的 REDIS_URL 是 http://host:port 形式，统一转换为
        redis://[:password@]host:port，密码为空则不附带认证段。
        """
        host_port = self.redis_url.split("://", 1)[-1].rstrip("/")
        auth = f":{self.redis_password}@" if self.redis_password else ""
        return f"redis://{auth}{host_port}"

    @property
    def mysql_dsn(self) -> str:
        """构造 SQLAlchemy async 引擎使用的 MySQL DSN。

        用户/密码经 URL 编码，避免特殊字符破坏 DSN；显式 utf8mb4
        与 LinkBetweenUs 后端的建库字符集保持一致。
        """
        from urllib.parse import quote_plus

        auth = f"{quote_plus(self.mysql_user)}:{quote_plus(self.mysql_password)}@"
        return (
            f"mysql+aiomysql://{auth}{self.mysql_host}:{self.mysql_port}/"
            f"{self.mysql_database}?charset=utf8mb4"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
