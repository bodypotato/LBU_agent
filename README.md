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
                                              │  ├─ tools: 内置 + MCP   │
                                              │  └─ checkpointer(记忆)  │
                                              └───┬─────────┬───────────┘
                                                  │         │
                                        Ollama (qwen3:4b)  Redis (会话持久化)
                                            │
                                            │ MCP(streamable HTTP :8765)
                                            ▼
                              ┌─────────────────────────────┐
                              │ lbu-tools MCP 服务(独立进程)  │
                              │  文件 / 时间 / 后端健康 / 联网  │
                              │  (后续: LBU 业务工具也走这里)   │
                              └─────────────────────────────┘
```

Agent 的工具体系规范化后分两层：

- **进程内置工具**：RAG 产品文档检索、技能加载（与 agent 配置/内存耦合）
- **MCP 工具**：通用能力（文件/时间/后端健康/联网）托管在 lbu-tools MCP 服务
  （独立进程），agent 经 `langchain-mcp-adapters` 动态加载；后续 LBU 业务工具
  （好友/聊天/群组等）同样走 MCP 接入，agent 侧不再逐个新增工具模块

## 项目结构

```
LBU_agent/
├── .env                     # 全部配置（create_agent 参数、agent 行为、LBU 后端地址）
├── main.py                  # FastAPI 入口（启动时预热 agent）
├── skills/                  # 技能目录：每个子目录一个技能（SKILL.md，对齐 Claude Code 用法）
├── app/
│   ├── config.py            # pydantic-settings 读取 .env
│   ├── schemas.py           # 请求/响应模型（沿用 LBU 的 Result{code,message,data} 约定）
│   ├── storage.py           # 历史对话存储（MySQL 落库，仅展示用，不参与上下文）
│   ├── agent/
│   │   ├── llm.py           # LLM 工厂（ChatOllama，参数来自 .env）
│   │   ├── prompt.py        # 贴合 LBU 的 system prompt（产品知识改走 RAG 检索）
│   │   ├── memory.py        # 会话记忆（Redis 持久化，thread_id 粒度，支持清空/压缩/回滚）
│   │   ├── rag.py           # RAG：docs/LBU.md 父子文档检索（Chroma + HuggingFace embedding）
│   │   ├── skills.py        # 技能系统：扫描 skills/ 下 SKILL.md，渐进披露 + /命令渲染
│   │   ├── mcp_client.py    # MCP 客户端：加载 lbu-tools 工具（不可达时降级）
│   │   ├── tools/           # 内置工具注册（__init__.py 统一注册入口）
│   │   │   ├── builtin.py   # RAG 产品文档检索
│   │   │   └── skill_tools.py # load_skill 技能加载
│   │   └── graph.py         # create_agent 构建 LangGraph agent（异步构建）
│   ├── mcp/                 # lbu-tools MCP 服务（通用能力工具宿主，独立进程）
│   │   ├── server.py        # FastMCP 服务（streamable HTTP，uv run python -m app.mcp.server）
│   │   ├── tools.py         # 通用工具：文件（工作区沙箱）/时间/后端健康/联网
│   │   └── process.py       # 主服务启动时自动拉起/回收 MCP 子进程
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
| `OLLAMA_NUM_CTX` | Ollama 上下文窗口（默认仅 4096，装不下工具定义，必须显式加大） | `16384` |
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
| `AGENT_WORKSPACE_DIR` | 文件工具读写根目录（相对进程工作目录） | `workspace` |
| `FILE_MAX_READ_CHARS` | `read_file` 单次返回的字符上限 | `8000` |
| `SKILLS_DIR` | 技能根目录（`<SKILLS_DIR>/<技能名>/SKILL.md`） | `skills` |
| `MCP_SERVER_PORT` | lbu-tools MCP 监听端口（仅 127.0.0.1） | `8765` |
| `MCP_SERVER_URL` | agent 客户端连接地址 | `http://127.0.0.1:8765/mcp` |
| `WEB_FETCH_TIMEOUT` | 网页抓取超时（秒） | `10` |
| `WEB_MAX_FETCH_CHARS` | `web_fetch` / `web_search` 单次返回内容的字符上限 | `12000` |
| `SERPER_API_KEY` | Serper.dev 的 API key（`web_search` 用 Google 搜索，serper.dev 注册获取） | 空 |
| `WEB_SEARCH_MAX_RESULTS` | `web_search` 单次返回的结果条数 | `8` |
| `WEB_SEARCH_REGION` | 搜索地区（Serper `gl` 参数） | `cn` |

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
| POST | `/api/agent/chat` | 对话。body: `{message, thread_id?, token?}`（token 也可走 `Authorization: Bearer` 头）；返回 `{reply, thread_id}`。成功后自动写入 MySQL 历史 |
| DELETE | `/api/agent/conversation/{thread_id}` | 清空会话上下文与历史记录 |
| GET | `/api/agent/history/{thread_id}` | 查询历史记录（仅展示用，按时间正序） |
| GET | `/api/agent/tools` | 列出已注册工具（内置 + MCP） |
| GET | `/api/agent/health` | 健康检查（含 Ollama 与 MCP 连通性，`data.mcp_reachable`） |

`thread_id` 是本 agent 自己的会话标识：同一用户与 AI 助手的连续对话传同一个
`thread_id` 即可延续上下文。

### LBU 业务工具（代替用户操作）

MCP 上还挂着 40 个业务工具（`app/mcp/lbu/`，按模块组织），覆盖人在 LBU
客户端里能做的操作：用户资料（改昵称/查资料）、好友（搜索/申请/同意/
拒绝/列表/删除/备注）、群组（建群/改名/解散/成员管理/禁言/入群审批/
群消息）、消息（单聊/群聊发送、聊天记录、会话列表、已读、删除）、在线状态。

**身份约定**：后端"登录即顶号"（每次登录使旧 token 失效），因此 agent
不自建凭证——调用方随 chat 请求把用户的 JWT 传过来（body 的 `token`
字段或 `Authorization: Bearer` 头），agent 按 thread_id 暂存到 Redis
（`lbu:agent:token:*`，TTL 48h），MCP 工具按会话取 token 调后端。
**token 不进入模型上下文**（拦截器注入 thread_id、工具侧查 Redis），
模型也无法伪造身份。token 过期（24h）或顶号后，工具会提示用户重新登录。

发消息走 STOMP WebSocket（后端无 REST 发消息端点），MCP 内实现最小
STOMP 客户端（CONNECT → SEND → 等回执），支持多端同时在线。

**小模型适配**（已实测校准）：qwen3:4b 面对 50 个工具时选择能力会失效，
两个必要措施——① `OLLAMA_NUM_CTX` 显式加大（Ollama 默认 4096 会截断
工具定义，症状是模型声称"没有这个功能"）；② system prompt 内置按类别
分组的工具目录（名称 + 一句话用途），帮助模型快速定位工具。

## 已注册工具

**进程内置**（agent 进程内注册）：

- `search_lbu_docs` — RAG 检索 LBU 产品文档（父子文档模式，LBU 产品问题优先走此工具）
- `load_skill` — 加载技能说明正文或技能目录下的资源文件（渐进披露）

**经 MCP（lbu-tools 服务）**：

- `list_files` — 列出工作区目录内容
- `read_file` — 读取工作区文本文件（超长截断）
- `write_file` — 写入/覆盖工作区文件（自动创建父目录）
- `append_file` — 向工作区文件追加内容
- `get_current_time` — 当前时间
- `check_lbu_backend_health` — 探测 LinkBetweenUs 后端在线状态
- `web_fetch` — 抓取网页转纯文本（超长截断，联网查询用）
- `web_search` — Google 搜索（Serper.dev，返回标题/链接/摘要与直接答案；未配置 key 时优雅降级）

### MCP（lbu-tools 工具服务）

工具体系规范化后，通用能力与后续业务能力都托管在 **MCP 服务**（官方
Python SDK 的 FastMCP，streamable HTTP 传输，仅监听 127.0.0.1），agent
经 `langchain-mcp-adapters` 动态加载工具，不再逐个写进 agent 进程：

- **启动**：主服务（main.py）启动时自动探测并拉起 MCP 子进程，退出时回收；
  也支持独立运行（`uv run python -m app.mcp.server`），供 Claude Desktop 等
  外部 MCP 客户端直连；
- **降级**：MCP 服务不可达时 agent 仍可用内置工具（RAG/技能）照常服务，
  只记日志；服务恢复后重启主服务即可重新挂载；
- **沙箱不变**：文件工具的工作区沙箱约束在 MCP 侧原样保留（越界路径拒绝）；
- **扩展**：新增通用工具只需在 `app/mcp/tools.py` 加函数并在 `register_tools`
  注册；后续 LBU 业务工具（好友/聊天/群组）也走 MCP 接入。

### 文件工具（工作区沙箱）

文件工具只在 `AGENT_WORKSPACE_DIR`（默认 `workspace/`，已 gitignore）内读写，
越出工作区的路径（绝对路径、`..` 跳级等）一律拒绝，防止 agent 误读写项目
源码或系统文件。`read_file` 单次最多返回 `FILE_MAX_READ_CHARS` 字符，超出
截断并提示，可分次续读。

### 技能系统（skill）

对齐 Claude Code 的 SKILL.md 用法，在 `SKILLS_DIR`（默认 `skills/`）下按目录
组织技能，每个技能一个 `SKILL.md`：首部 YAML frontmatter 写 `name`（可选）和
`description`（一句话，决定何时触发），正文是给模型的完整指令。技能目录下
除 SKILL.md 外的文件是资源文件，可用 `load_skill` 的 `resource` 参数按需读取。

触发方式：

- **斜杠命令（推荐，确定性）**：用户发 `/技能名 具体内容`，服务端自动把技能
  正文拼进消息，不依赖模型判断。已实测通过。
- **模型自选（渐进披露）**：技能清单（名称 + 描述）注入 system prompt，
  模型觉得相关时调用 `load_skill` 加载正文。机制已通，但 qwen3:4b 实测
  倾向直接用基础工具完成任务、跳过技能加载——小模型的自选触发不可靠，
  换更大模型（qwen3:8b/14b 或云端模型）后此路径会更好用。

技能正文写法建议：短小、中文、自然语言步骤，不要要求严格格式输出
（qwen3:4b 结构化输出不可靠）；复杂任务拆成多个小技能。新增技能后，
`load_skill` 工具与 /命令立即生效，system prompt 清单需重启服务刷新。
示例见 `skills/write-report/`。

## 扩展路线（按需逐步搭建）

1. **LBU 业务工具（走 MCP）**：在 lbu-tools MCP 服务中按后端模块组织（friend /
   chat / group / online / user），通过后端 REST API（JWT）读取真实数据，
   agent 侧零改动自动获得新工具。
2. **持久化记忆**：已完成 `InMemorySaver` → `AsyncRedisSaver`，会话历史落盘 Redis，
   服务重启上下文不丢；每次对话后调用 `aprune`（keep_latest）把 checkpoint
   压缩为每会话一条（覆盖式，非 TTL，不丢上下文）。
3. **图结构演进**：需要多节点编排 / 中断 / 多 agent 时，从 `create_agent`
   改为显式 `StateGraph` 或 `create_deep_agent`。
4. **后端对接**：在 Spring Boot 端新增独立的 agent 接入层，调用本服务（与既有
   Dify 通道并存，互不影响）。
