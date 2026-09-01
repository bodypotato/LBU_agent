"""Agent 构建：langchain.agents.create_agent（内部即 LangGraph 状态图）。

地基阶段使用 create_agent 的默认 LangGraph 结构（agent loop：模型 ↔ 工具），
后续需要定制（多节点编排、子图、中断、多 agent 等）时，可在此基于
langgraph 的 StateGraph 显式搭建，或替换成 create_deep_agent 等预构建方案。
"""

from functools import lru_cache

from langchain.agents import create_agent
from langchain_core.messages import AIMessage
from langgraph.graph.state import CompiledStateGraph

from app.agent.llm import get_llm
from app.agent.memory import memory
from app.agent.prompt import build_system_prompt
from app.agent.tools import get_tools


@lru_cache
def build_agent() -> CompiledStateGraph:
    """构建并编译 agent 图（进程内单例）。

    create_agent 的参数来源：
    - model           ← .env 的 OLLAMA_MODEL / OLLAMA_BASE_URL
    - tools           ← app/agent/tools.py 的注册表
    - system_prompt   ← app/agent/prompt.py（贴合 LBU 的人设）
    - checkpointer    ← ConversationMemory（thread_id 粒度会话记忆）
    """
    return create_agent(
        model=get_llm(),
        tools=get_tools(),
        system_prompt=build_system_prompt(),
        checkpointer=memory.checkpointer,
    )


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
