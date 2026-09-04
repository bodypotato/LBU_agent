"""Agent 构建：langchain.agents.create_agent（内部即 LangGraph 状态图）。

地基阶段使用 create_agent 的默认 LangGraph 结构（agent loop：模型 ↔ 工具），
后续需要定制（多节点编排、子图、中断、多 agent 等）时，可在此基于
langgraph 的 StateGraph 显式搭建，或替换成 create_deep_agent 等预构建方案。

工具来源：内置工具（RAG / 技能）+ lbu-tools MCP 服务（异步加载，见
app/agent/mcp_client.py），因此构建过程是异步的（进程内单例，首次 await 时构建）。

上下文裁剪：挂载 SummarizationMiddleware，消息数达到 SUMMARY_TRIGGER_MESSAGES
时把旧消息压缩为一段摘要（保留最新 SUMMARY_KEEP_MESSAGES 条）。裁剪结果作为
状态更新经 checkpointer 落盘 Redis，后续请求自动携带 [摘要 + 最新消息] 续聊；
摘要模型与对话模型共用（OLLAMA_MODEL）。
"""

from langchain.agents import create_agent
from langchain.agents.middleware import SummarizationMiddleware
from langchain_core.messages import AIMessage
from langgraph.graph.state import CompiledStateGraph

from app.agent.llm import get_llm
from app.agent.memory import memory
from app.agent.prompt import build_system_prompt
from app.agent.tools import get_tools
from app.config import get_settings

SUMMARY_PROMPT = """你是对话历史整理助手。请从下面的对话历史中提取最重要的信息，生成一段精炼的摘要。

要求：
- 用简体中文输出，保留用户提到的事实、需求、偏好、数字、名称等关键信息；
- 说明已经完成的事项与结论，避免后续重复工作；
- 只输出摘要正文，不要任何解释、标题或前缀。

对话历史：
{messages}
"""

_agent: CompiledStateGraph | None = None


async def build_agent() -> CompiledStateGraph:
    """构建并编译 agent 图（进程内单例，异步：需先加载 MCP 工具）。

    create_agent 的参数来源：
    - model           ← .env 的 OLLAMA_MODEL / OLLAMA_BASE_URL
    - tools           ← 内置工具 + lbu-tools MCP 工具（app/agent/tools.py）
    - system_prompt   ← app/agent/prompt.py（贴合 LBU 的人设）
    - checkpointer    ← ConversationMemory（thread_id 粒度会话记忆）
    - middleware      ← SummarizationMiddleware（超长上下文自动压缩）
    """
    global _agent
    if _agent is not None:
        return _agent
    settings = get_settings()
    llm = get_llm()
    tools = await get_tools()
    _agent = create_agent(
        model=llm,
        tools=tools,
        system_prompt=build_system_prompt([t.name for t in tools]),
        checkpointer=memory.checkpointer,
        middleware=[
            SummarizationMiddleware(
                model=llm,  # 摘要模型与对话模型共用
                trigger=("messages", settings.summary_trigger_messages),
                keep=("messages", settings.summary_keep_messages),
                summary_prompt=SUMMARY_PROMPT,
            )
        ],
    )
    return _agent


def extract_final_answer(result: dict) -> str:
    """从 agent 输出中提取最终回复文本。

    qwen3 是 thinking 模型，AIMessage 可能先带 reasoning_content 再带 content；
    取最后一条 AI 消息的 content，若为空（异常情况）则兜底给提示语。
    """
    messages: list = result.get("messages", [])
    for msg in reversed(messages):
        if isinstance(msg, AIMessage):
            content = msg.content
            if isinstance(content, list):  # 多模态片段
                content = "".join(
                    part.get("text", "") for part in content
                    if isinstance(part, dict)
                )
            if content and str(content).strip():
                return str(content)
    return "抱歉，我这次没有生成有效的回复，请稍后再试。"
