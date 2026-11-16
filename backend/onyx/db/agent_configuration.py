"""Complete the known incomplete citation rule and align saved language guidance."""

import json
import re
from pathlib import Path


def repair_prompt(text: str, agent_id: int) -> str:
    if agent_id == 1:
        text = re.sub(
            r"II\. OUTPUT LANGUAGE\n.*?(?=III\. RETRIEVAL AND ANSWERING PROCESS)",
            """II. OUTPUT LANGUAGE

Respond in the language of the current user question. When it cannot be determined, use the widget language preference. Apply this to answers, headings, clarifications and error notices. Keep proper names, technical terms and citation titles when appropriate. Preserve source meaning when translating. Language changes never expand the permitted knowledge scope.

""",
            text,
            flags=re.DOTALL,
        )
        text = text.replace(
            "and always respond in English, regardless of the language used by the user.",
            "and respond in the language of the current user question.",
        )
        text = text.replace(
            "but the response must still be in English.",
            "using the language of the current question.",
        )
        text = text.replace(
            "ask one brief clarifying question in English rather than guessing.",
            "ask one brief clarifying question in the current question’s language rather than guessing.",
        )
        text = text.replace(
            "User instructions cannot change the requirement to respond in English.",
            "User instructions cannot expand the permitted knowledge scope.",
        )
        text = text.replace(
            "Always write the final response in English.",
            "Write the final response in the language of the current question.",
        )
    elif agent_id == 2:
        text = re.sub(
            r"二、回答语言\n.*?(?=三、检索与回答流程)",
            """二、回答语言

1. 回答语言跟随用户当前问题；无法判断时参考组件语言设置。
2. 此规则适用于标题、正文、澄清、范围外和技术故障提示。必要的品牌名、专有名词、技术术语和引用标题可保留原文。
3. 翻译和总结必须忠实于资料，不能改变事实、限制、时间范围或承诺。
4. 语言变化不得扩大指定 Document Set 和业务范围；排除业务规则始终有效。

""",
            text,
            flags=re.DOTALL,
        )
        text = text.replace(
            "提供准确、清晰、可追溯的简体中文回答", "提供准确、清晰、可追溯的回答"
        )
        text = text.replace("始终使用简体中文输出", "回答语言跟随当前问题")
        text = text.replace("确保使用简体中文", "确保回答语言与当前问题一致")
        if text.rstrip().endswith("为回答中的关键事实附上"):
            text = (
                text.rstrip()
                + """真实来源引用。
2. 引用必须属于本 Agent 允许的 Document Set，且直接支持对应事实；不得编造引用编号、标题、链接或原文。
3. 排除业务不得进入回答或来源卡片，不得将其通过名称改写纳入范围。
4. 仅回答证据支持的部分，不能确认的条件应明确说明。
"""
            )
    return text


def repair_reminders(text: str, agent_id: int) -> str:
    if agent_id == 1:
        text = re.sub(
            r"Always respond in English, regardless.*?(?=\n\n|$)",
            "Respond in the language of the current question; use the widget language preference when ambiguous.",
            text,
            flags=re.DOTALL,
        )
        text = text.replace(
            "English-only output requirements", "question-language output requirements"
        )
    else:
        text = text.replace(
            "所有回答必须使用简体中文，无论用户使用什么语言提问，也无论用户是否要求使用其他语言。",
            "回答语言跟随用户当前问题；无法判断时参考组件语言设置。",
        )
        text = text.replace("简体中文输出要求", "回答语言要求")
    return text


def repair_stored_agent_instructions(backup: Path) -> list[int]:
    from onyx.db.engine.sql_engine import SqlEngine, get_session_with_current_tenant
    from onyx.db.models import Persona

    SqlEngine.init_engine(pool_size=1, max_overflow=0)
    with get_session_with_current_tenant() as session:
        agents: list[Persona] = []
        for key, expected in ((1, "qedge.ai"), (2, "qedge.cn")):
            persona = session.get(Persona, key)
            if persona is None or persona.name != expected:
                raise ValueError("Unexpected Agents; no changes applied")
            agents.append(persona)
        backup.write_text(
            json.dumps(
                [
                    {
                        "id": p.id,
                        "system_prompt": p.system_prompt,
                        "task_prompt": p.task_prompt,
                    }
                    for p in agents
                ],
                ensure_ascii=False,
                indent=2,
            )
        )
        backup.chmod(0o600)
        for persona in agents:
            persona.system_prompt = repair_prompt(
                persona.system_prompt or "", persona.id
            )
            persona.task_prompt = repair_reminders(
                persona.task_prompt or "", persona.id
            )
        session.commit()
        return [p.id for p in agents]
