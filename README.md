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
                                              └─────┬─────────┬───────┘
                                                    │         │
                                          Ollama (qwen3:4b)  Redis (会话持久化)
```

## 项目结构

```
LBU_agent/
├── .env                     # 全部配置（create_agent 参数、agent 行为、LBU 后端地址）
├── main.py                  # FastAPI 入口（启动时预热 agent）
├── app/
│   ├── config.py            # pydantic-settings 读取 .env
│   ├── schemas.py           # 请求/响应模型（沿用 LBU 的 Result{code,message,data} 约定）
│   ├── agent/
│   │   ├── llm.py           # LLM 工厂（ChatOllama，参数来自 .env）
│   │   ├── prompt.py        # 贴合 LBU 的 system prompt
│   │   ├── memory.py        # 会话记忆（Redis 持久化，thread_id 粒度，支持清空上下文）
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

## HTTP API

响应统一为 LinkBetweenUs 的 `Result` 约定：`{"code": 200, "message": "ok", "data": ...}`。

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/agent/chat` | 对话。body: `{message, thread_id?}`；返回 `{reply, thread_id}` |
| DELETE | `/api/agent/conversation/{thread_id}` | 清空会话上下文 |
| GET | `/api/agent/tools` | 列出已注册工具 |
| GET | `/api/agent/health` | 健康检查（含 Ollama 连通性） |

`thread_id` 是本 agent 自己的会话标识：同一用户与 AI 助手的连续对话传同一个
`thread_id` 即可延续上下文。

## 已注册工具（地基阶段）

- `get_current_time` — 当前时间
- `check_lbu_backend_health` — 探测 LinkBetweenUs 后端在线状态

## 扩展路线（按需逐步搭建）

1. **LBU 业务工具**：在 `app/agent/tools/` 下按后端模块组织（friend / chat / group /
   online / user），通过后端 REST API（JWT）读取真实数据。
2. **持久化记忆**：已完成 `InMemorySaver` → `AsyncRedisSaver`，会话历史落盘 Redis，
   服务重启上下文不丢；后续可考虑为 checkpoint 配置 TTL 或按用户维度清理。
3. **图结构演进**：需要多节点编排 / 中断 / 多 agent 时，从 `create_agent`
   改为显式 `StateGraph` 或 `create_deep_agent`。
4. **后端对接**：在 Spring Boot 端新增独立的 agent 接入层，调用本服务（与既有
   Dify 通道并存，互不影响）。
