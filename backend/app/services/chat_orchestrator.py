from __future__ import annotations

import logging
from typing import Iterator

from app.schemas.chat import ChatResponse, ClassificationResult
from app.services.agent_orchestrator import AgentOrchestrator
from app.services.query_analyzer import QueryAnalyzer
from app.services.streaming import build_end_event, build_progress_event, build_start_event, build_text_chunk_event


logger = logging.getLogger(__name__)


class ChatOrchestrator:
    def __init__(
        self,
        query_analyzer: QueryAnalyzer,
        agent_orchestrator: AgentOrchestrator,
    ) -> None:
        self.query_analyzer = query_analyzer
        self.agent_orchestrator = agent_orchestrator

    def respond(self, user_id: str, message: str) -> ChatResponse:
        analysis = self.query_analyzer.analyze(message)
        execution = self.agent_orchestrator.execute(user_id=user_id, message=message, analysis=analysis)
        logger.info(
            "chat_request_routed trace_id=%s user_id=%s query_type=%s execution_mode=%s tool_calls=%s retrieval_used=%s",
            execution.trace.trace_id,
            user_id,
            execution.trace.query_type,
            execution.trace.execution_mode,
            execution.trace.tool_calls,
            execution.trace.retrieval_used,
        )
        return execution.response

    def stream_response(self, user_id: str, message: str) -> Iterator[str]:
        yield build_start_event()
        analysis = self.query_analyzer.analyze(message)
        yield build_progress_event(
            "classification",
            category=analysis.category,
            normalized_message=analysis.normalized_message,
        )
        gateway_request, plan = yield from self._stream_gateway_request_events(
            user_id=user_id,
            message=message,
            analysis=analysis,
        )

        chunk_index = 0
        for chunk in self.agent_orchestrator.response_composer.model_gateway.stream(gateway_request):
            if not chunk:
                continue
            yield build_text_chunk_event(index=chunk_index, delta=chunk)
            chunk_index += 1
        yield build_end_event(
            query_type=plan.query_type,
            execution_mode=plan.execution_mode,
            streamed_chunks=chunk_index,
        )

    def _stream_gateway_request_events(
        self,
        user_id: str,
        message: str,
        analysis: ClassificationResult,
    ) -> Iterator[str]:
        generator = self.agent_orchestrator.stream_gateway_request(
            user_id=user_id,
            message=message,
            analysis=analysis,
        )
        while True:
            try:
                event_name, data = next(generator)
            except StopIteration as stop:
                return stop.value
            yield build_progress_event(event_name, **data)
