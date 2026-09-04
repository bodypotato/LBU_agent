# LBU Agent

LinkBetweenUs 的 AI 智能助手服务。基于 **Python + LangChain + LangGraph** 构建，
对接本机 **Ollama**（qwen3:4b）。**独立于后端 Dify 方案的 agent**，拥有自己的
会话记忆、工具体系和扩展路线。

## 架构

```
┌────────────────┐      ┌─────────────────────┐      ┌──────────┐
│ LBU Client     │      │ LinkBetweenUs        │      │ LBU Agent│
│ (Electron)     │─────▶│ (Spring Boot :8080)  │─────▶│ (FastAPI  │
│                │      │  独立 agent 接入层   │      │  :8000)  │
└────────────────┘      └─────────────────────┘      └────┬─────┘
                                                          │
                                              ┌───────────┴───────────┐
                                              │ LangGraph 状态图        │
                                              │  create_agent          │
                                              │  ├─ model: ChatOllama  │
                                              │  ├─ tools: 内置+LBU工具 │
                                              │  └─ checkpointer(记忆)  │
                                              └─────┬─────────┬───────────┘
                                                    │         │
                                          Ollama (qwen3:4b)  Redis (会话持久化)
                                                              │
                                                    ┌─────────┴─────────────────┐
                                                    │ RAG（父子文档检索）        │
                                                    │  docs/LBU.md ─▶ Chroma 向量库│
                                                    │  + Qwen3-Embedding-0.6B   │
                                                    └───────────────────────────┘
```

## 项目结构

```
LBU_agent/
├── .env                     # 全部配置（create_agent 参数、agent 行为、LBU 后端地址）
├── main.py                  # FastAPI 入口（启动时预热 agent）
├── app/
│   ├── config.py            # pydantic-settings 读取 .env
│   ├── schemas.py           # 请求/响应模型（沿用 LBU 的 Result{code,message,data} 约定）
│   ├── storage.py           # 历史对话存储（MySQL 落库，仅展示用，不参与上下文）
│   ├── agent/
│   │   ├── llm.py           # LLM 工厂（ChatOllama，参数来自 .env）
│   │   ├── prompt.py        # 贴合 LBU 的 system prompt（产品知识改走 RAG 检索）
│   │   ├── memory.py        # 会话记忆（Redis 持久化，thread_id 粒度，支持清空/压缩/回滚）
│   │   ├── rag.py           # RAG：docs/LBU.md 父子文档检索（Chroma + HuggingFace embedding）
│   │   ├── tools.py         # 工具注册（内置工具 + 后续 LBU 业务工具）
│   │   └── graph.py         # create_agent 构建 LangGraph agent
│   └── api/
│       └── routes.py        # HTTP API（/api/agent/*）
└── test_main.http           # 接口自测脚本（REST Client）
```

## 快速开始

```bash
# 1. 依赖安装（已有 .venv）
uv sync

# 2. 确认 Ollama 已启动且模型已拉取
ollama list   # 应包含 qwen3:4b

# 3. 启动服务
uv run uvicorn main:app --reload --port 8000
```

配置都在 `.env`（已 gitignore）：

| 变量 | 说明 | 默认值 |
|---|---|---|
| `OLLAMA_MODEL` | create_agent 的 model 来源 | `qwen3:4b` |
| `OLLAMA_BASE_URL` | OpenAI 兼容格式地址（内部自动转换为 Ollama 原生地址） | `http://localhost:11434/v1` |
| `AGENT_NAME` | agent 自称 | `LBU 助手` |
| `AGENT_TEMPERATURE` | 采样温度 | `0.7` |
| `AGENT_TIMEOUT` | LLM 单次请求超时（秒） | `120` |
| `LBU_BACKEND_BASE_URL` | LinkBetweenUs 后端地址（工具对接用） | `http://localhost:8080` |
| `REDIS_URL` | Redis 地址（会话 checkpointer 持久化） | `http://localhost:6379` |
| `REDIS_PASSWORD` | Redis 密码（为空则不认证） | 空 |
| `MYSQL_HOST` | MySQL 地址（历史对话存储，仅展示用） | `localhost` |
| `MYSQL_PORT` | MySQL 端口 | `3306` |
| `MYSQL_DATABASE` | 库名（与 LinkBetweenUs 共用同一实例） | `Link_Between_Us` |
| `MYSQL_USER` | MySQL 用户 | `root` |
| `MYSQL_PASSWORD` | MySQL 密码 | 空 |
| `EMBEDDING_MODEL_NAME` | RAG embedding 模型（HuggingFace） | `Qwen/Qwen3-Embedding-0.6B` |
| `EMBEDDING_DEVICE` | embedding 推理设备 | `cpu` |
| `CHROMA_PERSIST_DIR` | Chroma 向量库持久化目录 | `./chroma_db` |
| `RAG_DOC_DIR` | RAG 文档目录（全部 .md 均为文档源） | `docs` |
| `RAG_TOP_K` | 单次检索返回的父文档数 | `4` |
| `SUMMARY_TRIGGER_MESSAGES` | 消息数达到该值时触发上下文压缩 | `20` |
| `SUMMARY_KEEP_MESSAGES` | 压缩后保留的最新消息数 | `4` |

历史记录写入独立表 `LBU_Agent_Message`（启动时自动建表），与后端 `LBU_Message`
互不干扰；MySQL 暂不可用时服务照常启动，仅历史功能降级。

### RAG（产品文档检索增强）

父子文档模式：`RAG_DOC_DIR` 下全部 .md 先按 Markdown 标题（#/##/###/####）
切成父文档，每个父文档再按 200 字 chunk / 50 字重合切成子文档写入 Chroma；
检索时子文档命中后映射回父文档去重返回。多文档按文件分类存储（source=文件
路径、category=所在目录），检索默认全库、可按分类过滤。按文件 md5 增量重建：
新增/修改的文件只重建自己，删除的文件自动清理向量，互不覆盖。首次运行需从
HuggingFace 下载 embedding 模型（约 1.2GB）。

### 上下文裁剪（SummarizationMiddleware）

消息数达到 `SUMMARY_TRIGGER_MESSAGES`（20）时，把旧消息压缩为一段中文摘要，
仅保留最新 `SUMMARY_KEEP_MESSAGES`（4）条。裁剪是状态级更新：经 checkpointer
落盘 Redis，后续请求自动携带 [摘要 + 最新消息] 续聊，不会丢失关键信息；
摘要模型与对话模型共用 `OLLAMA_MODEL`。MySQL 中的完整历史不受裁剪影响。

## HTTP API

响应统一为 LinkBetweenUs 的 `Result` 约定：`{"code": 200, "message": "ok", "data": ...}`。

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/agent/chat` | 对话。body: `{message, thread_id?}`；返回 `{reply, thread_id}`。成功后自动写入 MySQL 历史 |
| DELETE | `/api/agent/conversation/{thread_id}` | 清空会话上下文与历史记录 |
| GET | `/api/agent/history/{thread_id}` | 查询历史记录（仅展示用，按时间正序） |
| GET | `/api/agent/tools` | 列出已注册工具 |
| GET | `/api/agent/health` | 健康检查（含 Ollama 连通性） |

`thread_id` 是本 agent 自己的会话标识：同一用户与 AI 助手的连续对话传同一个
`thread_id` 即可延续上下文。

## 已注册工具（地基阶段）

- `get_current_time` — 当前时间
- `check_lbu_backend_health` — 探测 LinkBetweenUs 后端在线状态
- `search_lbu_docs` — RAG 检索 LBU 产品文档（父子文档模式，LBU 产品问题优先走此工具）

## 扩展路线（按需逐步搭建）

1. **LBU 业务工具**：在 `app/agent/tools/` 下按后端模块组织（friend / chat / group /
   online / user），通过后端 REST API（JWT）读取真实数据。
2. **持久化记忆**：已完成 `InMemorySaver` → `AsyncRedisSaver`，会话历史落盘 Redis，
   服务重启上下文不丢；每次对话后调用 `aprune`（keep_latest）把 checkpoint
   压缩为每会话一条（覆盖式，非 TTL，不丢上下文）。
3. **图结构演进**：需要多节点编排 / 中断 / 多 agent 时，从 `create_agent`
   改为显式 `StateGraph` 或 `create_deep_agent`。
4. **后端对接**：在 Spring Boot 端新增独立的 agent 接入层，调用本服务（与既有
   Dify 通道并存，互不影响）。
