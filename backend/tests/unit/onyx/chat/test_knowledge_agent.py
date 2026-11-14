"""Preserve QEdge behavior across runtime execution, Stop, and replay."""

import json
from unittest.mock import Mock
from uuid import uuid4

import pytest

from onyx.agents.models import (
    AgentState,
    ExecutionCheckpoint,
    RunProgress,
    RunState,
    RunStatus,
)
from onyx.agents.tools import ToolInvocation
from onyx.chat.emitter import Emitter
from onyx.chat.knowledge_agent import KnowledgeAgent, KnowledgeFeatureState
from onyx.chat.knowledge_rag import knowledge_route_enabled
from onyx.chat.models import ChatTurnSetup, PersonaPromptConfig, SearchParams
from onyx.chat.presentation import ResponsePresenter, project_response
from onyx.configs.constants import DocumentSource
from onyx.context.search.models import SearchDoc, SearchDocsResponse
from onyx.llm.cancellation import CancellationSignal
from onyx.llm.interfaces import LLM, LLMConfig
from onyx.llm.models import AssistantMessage, TextContent, ToolResult, UserMessage
from onyx.server.query_and_chat.models import SendMessageRequest
from onyx.server.query_and_chat.streaming_models import Packet
from onyx.tools.models import SearchToolUsage, ToolContext
from tests.unit.onyx.agents.fakes import EchoTool


class KnowledgeSearch(EchoTool):
    def __init__(self, *, empty: bool = False) -> None:
        self.empty = empty
        self.contexts: list[ToolContext] = []

    @property
    def name(self) -> str:
        return "internal_search"

    def _run(self, invocation: ToolInvocation, context: ToolContext) -> ToolResult:
        invocation.cancellation.check()
        self.contexts.append(context)
        docs = (
            []
            if self.empty
            else [
                SearchDoc(
                    document_id="https://qedge.ai/services",
                    chunk_ind=0,
                    semantic_identifier="QEdge services",
                    link="https://qedge.ai/services",
                    blurb="Sitecore services",
                    source_type=DocumentSource.WEB,
                    boost=1,
                    hidden=False,
                    metadata={},
                    match_highlights=[],
                )
            ]
        )
        return ToolResult(
            content=json.dumps(
                {
                    "results": []
                    if self.empty
                    else [
                        {
                            "document": 1,
                            "title": "Services",
                            "content": "QEdge provides Sitecore implementation.",
                        }
                    ]
                }
            ),
            details=SearchDocsResponse(
                search_docs=docs,
                displayed_docs=docs,
                citation_mapping={1: docs[0].document_id} if docs else {},
            ),
        )


def make_agent(
    *, empty: bool = False, deep: bool = False
) -> tuple[KnowledgeAgent, Mock, KnowledgeSearch]:
    llm = Mock(spec=LLM)
    llm.config = LLMConfig(
        model_provider="openai",
        model_name="test-flash",
        max_input_tokens=100_000,
        temperature=0,
    )
    llm.redact_error.side_effect = lambda text: text
    llm.invoke.return_value = AssistantMessage(
        content=[TextContent(text="我们提供 Sitecore 实施服务。[1]")]
    )
    tool = KnowledgeSearch(empty=empty)
    agent = KnowledgeAgent(
        llm=llm,
        tools=[tool],
        settings=KnowledgeFeatureState(
            persona=PersonaPromptConfig(
                system_prompt="Always answer in English.",
                task_prompt="",
                datetime_aware=False,
                replace_base_system_prompt=False,
            ),
            force_deep=deep,
        ),
        state=AgentState(
            messages=[
                UserMessage(content="Sitecore services"),
                AssistantMessage(
                    content=[
                        TextContent(text="Unsupported old answer: we operate on Mars.")
                    ]
                ),
            ]
        ),
        agent_id="knowledge-test",
        previous_run_id=None,
        user_identity=None,
    )
    return agent, llm, tool


@pytest.mark.parametrize("deep", [False, True])
def test_one_flash_call_preserves_streamed_answer_and_replay(deep: bool) -> None:
    agent, llm, tool = make_agent(deep=deep)
    packets: list[Packet] = []
    presenter = ResponsePresenter(
        Emitter(packets.append), tool_ids={tool.name: tool.id}
    )
    run = agent.start(
        messages=[UserMessage(content="QEdge 提供哪些服务？")],
        max_steps=agent.max_steps,
        on_event=presenter.consume,
    )
    try:
        run.result(timeout=10)
        snapshot = run.snapshot()
        assert snapshot.status == RunStatus.COMPLETE
        assert len(snapshot.steps) == 2
        llm.invoke.assert_called_once()
        llm.stream.assert_not_called()
        request = llm.invoke.call_args.args[0]
        assert "Mars" not in request.model_dump_json()
        assert request.system_prompt.endswith("仅使用简体中文回答。")
        assert "we/our" in request.system_prompt
        assert tool.contexts[0].grounded_fast_mode
        replay = project_response(snapshot, tool_ids={tool.name: tool.id})
        assert "实施服务" in (replay.answer or "")
        assert len(replay.tool_calls) == 1
        assert replay.tool_calls[0].search_docs
        assert replay.citation_to_doc[1].document_id == "https://qedge.ai/services"
        assert any(packet.obj.type == "search_tool_start" for packet in packets)
        assert any(packet.obj.type == "message_delta" for packet in packets)
    finally:
        assert run.wait_for_idle(timeout=10)


def test_missing_evidence_makes_no_provider_call() -> None:
    agent, llm, _ = make_agent(empty=True, deep=True)
    run = agent.start(
        messages=[UserMessage(content="请比较未知内容")], max_steps=agent.max_steps
    )
    try:
        result = run.result(timeout=10)
        assert result.stop_reason == RunStatus.COMPLETE
        llm.invoke.assert_not_called()
        llm.stream.assert_not_called()
        assert "无法确认" in result.output.text
    finally:
        assert run.wait_for_idle(timeout=10)


def test_stop_rejects_generated_answer() -> None:
    agent, llm, _ = make_agent()
    cancellation = CancellationSignal()

    def cancel_during_generation(*_args: object, **_kwargs: object) -> AssistantMessage:
        cancellation.cancel()
        return AssistantMessage(content=[TextContent(text="Late answer [1]")])

    llm.invoke.side_effect = cancel_during_generation
    run = agent.start(
        messages=[UserMessage(content="Sitecore 服务")],
        max_steps=agent.max_steps,
        cancellation=cancellation,
    )
    try:
        assert run.wait_for_idle(timeout=10)
        snapshot = run.snapshot()
        assert snapshot.status == RunStatus.CANCELLED
        assert all("Late answer" not in step.message.text for step in snapshot.steps)
    finally:
        assert run.wait_for_idle(timeout=10)


@pytest.mark.parametrize("deep", [False, True])
def test_execution_dispatches_knowledge_before_deep_research(
    deep: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    from onyx.chat.execution import create_chat_agent

    agent, llm, tool = make_agent(deep=deep)
    monkeypatch.setattr("onyx.chat.knowledge_rag.PERSONAS", frozenset({2}))
    construct = Mock(return_value={"search": [tool]})
    monkeypatch.setattr("onyx.chat.execution.construct_tools", construct)
    setup = ChatTurnSetup.model_construct(
        new_msg_req=SendMessageRequest.model_validate(
            {"message": "QEdge 服务", "deep_research": deep}
        ),
        responses=[Mock(llm=llm)],
        incognito_record_mode=None,
        chat_session_id=uuid4(),
        chat_session_project_id=None,
        tool_configuration=Mock(),
        search_params=SearchParams(
            project_id_filter=None,
            persona_id_filter=None,
            search_usage=SearchToolUsage.AUTO,
        ),
        slack_context=None,
        user_message_id=1,
        custom_tool_additional_headers=None,
        mcp_headers=None,
        available_files=Mock(user_file_ids=[], chat_file_ids=[]),
        chat_files_for_tools=[],
        preferred_tool_id=None,
        persona_id=2,
        persona=agent.settings.persona,
        messages=[],
        previous_run_id=None,
        user_identity=None,
    )
    dispatched = create_chat_agent(
        setup, Mock(), 0, CancellationSignal(), False, with_subagents=False
    )
    assert isinstance(dispatched, KnowledgeAgent)
    assert dispatched.settings.force_deep == deep


def test_saved_knowledge_configuration_restores_same_route() -> None:
    from onyx.chat.restoration import restore_chat_agent

    agent, llm, tool = make_agent(deep=True)
    checkpoint = ExecutionCheckpoint(
        agent_state=AgentState(),
        run_state=RunState(
            run_id="saved-run",
            agent_id=agent.id,
            status=RunStatus.SUSPENDED,
            progress=RunProgress(
                step_limit=2,
                tool_configuration_digest="test-tools",
                feature_state=agent.capture_state().model_dump(mode="json"),
            ),
        ),
    )
    restored = restore_chat_agent(checkpoint, llm=llm, tools=[tool], user_identity=None)
    assert isinstance(restored, KnowledgeAgent)
    assert restored.capture_state() == agent.capture_state()


def test_model_selection_keeps_configured_flash_and_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from onyx.chat.knowledge_rag import summary_request_policy
    from onyx.chat.process_message import _select_models

    _, llm, _ = make_agent()
    monkeypatch.setattr("onyx.chat.knowledge_rag.PERSONAS", frozenset({2}))
    monkeypatch.setenv("QEDGE_RAG_MODEL_PROVIDER", "SiliconFlow")
    monkeypatch.setenv("QEDGE_RAG_SUMMARY_MODEL", "deepseek-flash")
    factory = Mock(return_value=llm)
    monkeypatch.setattr("onyx.chat.process_message.get_llm_for_persona", factory)
    monkeypatch.setattr(
        "onyx.chat.process_message.check_llm_cost_limit_for_provider", Mock()
    )
    monkeypatch.setattr("onyx.chat.process_message.check_model_spend_limits", Mock())
    session = Mock(
        persona_id=2, project_id=None, incognito_record_mode=None, llm_override=None
    )
    _select_models(
        SendMessageRequest.model_validate(
            {"message": "QEdge 服务", "deep_research": True}
        ),
        session,
        Mock(),
        None,
        None,
        Mock(),
    )
    override = factory.call_args.kwargs["llm_override"]
    assert override.model_version == "deepseek-flash"
    assert factory.call_args.kwargs["policy_fn"] is summary_request_policy


@pytest.mark.parametrize(
    ("model_count", "has_files", "project_id", "incognito"),
    [
        (2, False, None, False),
        (1, True, None, False),
        (1, False, 1, False),
        (1, False, None, True),
    ],
)
def test_standard_routes_are_not_replaced(
    model_count: int,
    has_files: bool,
    project_id: int | None,
    incognito: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("onyx.chat.knowledge_rag.PERSONAS", frozenset({2}))
    assert knowledge_route_enabled(
        2, model_count=1, has_files=False, project_id=None, incognito=False
    )
    assert not knowledge_route_enabled(
        2,
        model_count=model_count,
        has_files=has_files,
        project_id=project_id,
        incognito=incognito,
    )
