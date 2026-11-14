"""Run evidence-only answers through the shared chat execution records."""

import time
from collections.abc import Generator, Mapping, Sequence
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, JsonValue

from onyx.agents.models import AgentState, PreparedStep, StepInput
from onyx.agents.runtime import Agent, RestorableFeature
from onyx.chat.knowledge_rag import (
    focus_query,
    resolve_question,
    synthesize_knowledge_answer,
)
from onyx.chat.models import ChatMessageMetadata, PersonaPromptConfig
from onyx.context.search.models import SearchDoc, SearchDocsResponse
from onyx.error_handling.error_codes import OnyxErrorCode
from onyx.error_handling.exceptions import OnyxError
from onyx.llm.interfaces import LLM, GenerationContext, LLMConfig, LLMUserIdentity
from onyx.llm.models import (
    AssistantMessage,
    GenerationDoneEvent,
    GenerationEvent,
    GenerationRequest,
    GenerationRequestParams,
    Message,
    ReasoningEffort,
    TextContent,
    TextDeltaEvent,
    ToolCall,
    ToolCallEndEvent,
    ToolCallStartEvent,
    ToolResultMessage,
    UserMessage,
)
from onyx.tools.interface import Tool
from onyx.tools.models import ToolContext
from onyx.tracing.flows import LLMFlow


class KnowledgeFeatureState(BaseModel):
    kind: Literal["qedge.knowledge.v1"] = "qedge.knowledge.v1"
    persona: PersonaPromptConfig
    force_deep: bool = False
    include_citations: bool = True
    response_language: Literal["en", "zh"] | None = None


class _KnowledgeGeneration(LLM):
    """Make the fixed search step free, then validate one synthesis call."""

    def __init__(self, llm: LLM, settings: KnowledgeFeatureState) -> None:
        self.llm = llm
        self.settings = settings
        self.request_params: GenerationRequestParams | None = None

    @property
    def config(self) -> LLMConfig:
        return self.llm.config

    def redact_error(self, text: str) -> str:
        return self.llm.redact_error(text)

    def invoke(
        self, request: GenerationRequest, context: GenerationContext | None = None
    ) -> AssistantMessage:
        del request, context
        raise ValueError("Knowledge routing cannot summarize conversation history")

    def _answer(
        self, request: GenerationRequest, context: GenerationContext | None
    ) -> AssistantMessage:
        if context is not None and context.cancellation is not None:
            context.cancellation.check()
        results = [m for m in request.messages if isinstance(m, ToolResultMessage)]
        if not results:
            return AssistantMessage(
                content=[
                    ToolCall(
                        id=str(uuid4()),
                        name="internal_search",
                        arguments={
                            "queries": [focus_query(resolve_question(request.messages))]
                        },
                    )
                ]
            )
        users = [m for m in request.messages if isinstance(m, UserMessage)]
        answer = synthesize_knowledge_answer(
            question=resolve_question(users),
            current_question=resolve_question(users[-1:]),
            response=results[-1],
            persona=self.settings.persona,
            llm=self.llm,
            force_deep=self.settings.force_deep,
            include_citations=self.settings.include_citations,
            response_language=self.settings.response_language,
            context=context,
        )
        self.request_params = GenerationRequestParams(
            model_name=self.config.model_name,
            model_provider=self.config.model_provider,
            reasoning_effort=ReasoningEffort.OFF,
            max_tokens=1800 if self.settings.force_deep else 1100,
            sent_kwargs=answer.request_params,
        )
        return AssistantMessage(
            content=[TextContent(text=answer.answer)], usage=answer.usage
        )

    def stream(
        self, request: GenerationRequest, context: GenerationContext | None = None
    ) -> Generator[GenerationEvent, None, None]:
        message = self._answer(request, context)
        for index, block in enumerate(message.content):
            if isinstance(block, TextContent):
                yield TextDeltaEvent(content_index=index, text=block.text)
            elif isinstance(block, ToolCall):
                yield ToolCallStartEvent(
                    content_index=index, tool_call_id=block.id, tool_name=block.name
                )
                yield ToolCallEndEvent(content_index=index, tool_call=block)
        yield GenerationDoneEvent(
            usage=message.usage, request_params=self.request_params
        )


class KnowledgeAgent(Agent, RestorableFeature):
    """Keep search, rendering, Stop, save, and replay in the shared runtime."""

    max_steps = 2

    def __init__(
        self,
        *,
        llm: LLM,
        tools: list[Tool],
        settings: KnowledgeFeatureState,
        state: AgentState,
        agent_id: str | None,
        previous_run_id: str | None,
        user_identity: LLMUserIdentity | None,
    ) -> None:
        search = next((tool for tool in tools if tool.name == "internal_search"), None)
        if search is None:
            raise OnyxError(
                OnyxErrorCode.VALIDATION_ERROR,
                "Knowledge mode requires the configured internal search tool",
            )
        self.settings = settings
        self.configured_tools = [search]
        self.application_tools = [search]
        self.initial_citations: dict[int, SearchDoc] = {}
        self.started = time.monotonic()
        super().__init__(
            _KnowledgeGeneration(llm, settings),
            agent_id=agent_id,
            previous_run_id=previous_run_id,
            state=state,
            tools=[search.bind(lambda: ToolContext(grounded_fast_mode=True))],
            generation_context=GenerationContext(
                flow=LLMFlow.KNOWLEDGE_SYNTHESIS, user_identity=user_identity
            ),
            prepare_step=self._prepare_step,
            restoration=self,
        )

    def capture_state(self) -> KnowledgeFeatureState:
        return self.settings

    def restore_state(self, state: Mapping[str, JsonValue]) -> None:
        if KnowledgeFeatureState.model_validate(state) != self.settings:
            raise ValueError("Knowledge restoration configuration does not match")

    def _prepare_step(self, step: StepInput) -> PreparedStep:
        sources: dict[int, SearchDoc] = {}
        documents: list[SearchDoc] = []
        for result in step.messages:
            if isinstance(result, ToolResultMessage) and isinstance(
                result.details, SearchDocsResponse
            ):
                documents = result.details.displayed_docs or result.details.search_docs
                by_id = {doc.document_id: doc for doc in documents}
                sources.update(
                    {
                        number: by_id[doc_id]
                        for number, doc_id in result.details.citation_mapping.items()
                        if doc_id in by_id
                    }
                )

        def evidence_history(_messages: Sequence[Message]) -> list[Message]:
            # Only user questions resolve follow-ups; previous answers are never evidence.
            users = [
                m
                for m in [*step.history, *step.input_messages]
                if isinstance(m, UserMessage)
            ]
            return [*users[-2:], *step.messages]

        return PreparedStep(
            input_messages=[],
            allowed_tool_names=frozenset({"internal_search"})
            if step.previous is None
            else frozenset(),
            assemble_messages=evidence_history,
            output_metadata=ChatMessageMetadata(
                sources=sources,
                documents=documents,
                include_citations=self.settings.include_citations,
                elapsed_seconds=time.monotonic() - self.started,
            ),
        )
