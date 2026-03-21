from __future__ import annotations

import logging
from time import perf_counter
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
        started_at = perf_counter()
        analysis_started_at = perf_counter()
        analysis = self.query_analyzer.analyze(message)
        analysis_duration_ms = int((perf_counter() - analysis_started_at) * 1000)
        execution_started_at = perf_counter()
        execution = self.agent_orchestrator.execute(user_id=user_id, message=message, analysis=analysis)
        execution_duration_ms = int((perf_counter() - execution_started_at) * 1000)
        total_duration_ms = int((perf_counter() - started_at) * 1000)
        execution.trace.stage_timings_ms["query_analysis"] = analysis_duration_ms
        execution.trace.stage_timings_ms["agent_orchestrator"] = execution_duration_ms
        execution.trace.total_duration_ms = total_duration_ms
        logger.info(
            "chat_request_routed trace_id=%s user_id=%s query_type=%s execution_mode=%s tool_calls=%s retrieval_used=%s total_request_ms=%s stage_timings_ms=%s",
            execution.trace.trace_id,
            user_id,
            execution.trace.query_type,
            execution.trace.execution_mode,
            execution.trace.tool_calls,
            execution.trace.retrieval_used,
            total_duration_ms,
            execution.trace.stage_timings_ms,
        )
        return execution.response

    def stream_response(self, user_id: str, message: str) -> Iterator[str]:
        started_at = perf_counter()
        yield build_start_event()
        analysis_started_at = perf_counter()
        analysis = self.query_analyzer.analyze(message)
        analysis_duration_ms = int((perf_counter() - analysis_started_at) * 1000)
        yield build_progress_event(
            "classification",
            category=analysis.category,
            normalized_message=analysis.normalized_message,
            duration_ms=analysis_duration_ms,
        )
        orchestration_started_at = perf_counter()
        gateway_request, plan = yield from self._stream_gateway_request_events(
            user_id=user_id,
            message=message,
            analysis=analysis,
        )
        orchestration_duration_ms = int((perf_counter() - orchestration_started_at) * 1000)

        chunk_index = 0
        first_chunk_latency_ms: int | None = None
        for chunk in self.agent_orchestrator.response_composer.model_gateway.stream(gateway_request):
            if not chunk:
                continue
            if first_chunk_latency_ms is None:
                first_chunk_latency_ms = int((perf_counter() - started_at) * 1000)
            yield build_text_chunk_event(index=chunk_index, delta=chunk)
            chunk_index += 1
        yield build_end_event(
            query_type=plan.query_type,
            execution_mode=plan.execution_mode,
            streamed_chunks=chunk_index,
            total_request_ms=int((perf_counter() - started_at) * 1000),
            query_analysis_ms=analysis_duration_ms,
            planner_orchestrator_ms=orchestration_duration_ms,
            first_byte_latency_ms=first_chunk_latency_ms or int((perf_counter() - started_at) * 1000),
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
