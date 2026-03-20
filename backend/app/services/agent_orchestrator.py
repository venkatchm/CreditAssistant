from __future__ import annotations

import logging
from time import perf_counter
from uuid import uuid4

from app.schemas.chat import (
    AgentExecutionResult,
    ClassificationResult,
    ExecutionPlan,
    ExecutionStep,
    RetrievalResult,
    ToolResult,
    TraceContext,
)
from app.services.evidence_builder import EvidenceBuilder
from app.services.execution_planner import ExecutionPlanner
from app.services.grounded_response_composer import GroundedResponseComposer
from app.services.rag_service import RagService
from app.services.tool_registry import ToolRegistry


logger = logging.getLogger(__name__)


class AgentOrchestrator:
    def __init__(
        self,
        planner: ExecutionPlanner,
        tool_registry: ToolRegistry,
        rag_service: RagService,
        evidence_builder: EvidenceBuilder,
        response_composer: GroundedResponseComposer,
    ) -> None:
        self.planner = planner
        self.tool_registry = tool_registry
        self.rag_service = rag_service
        self.evidence_builder = evidence_builder
        self.response_composer = response_composer
        self._last_trace: TraceContext | None = None

    def execute(self, user_id: str, message: str, analysis: ClassificationResult) -> AgentExecutionResult:
        started_at = perf_counter()
        plan = self.planner.build_plan(analysis=analysis, message=message)
        trace = TraceContext(
            trace_id=str(uuid4()),
            user_id=user_id,
            query_type=analysis.category,
            execution_mode=plan.execution_mode,
            response_strategy=plan.response_strategy,
        )
        trace.steps.append(
            ExecutionStep(
                name="query_analysis",
                kind="classify",
                status="completed",
                detail=f"Query classified as {analysis.category}.",
            )
        )

        tool_results: dict[str, ToolResult] = {}
        retrieval_result: RetrievalResult | None = None

        for iteration in range(plan.max_iterations):
            for tool_name in plan.tool_names:
                if tool_name not in tool_results:
                    tool_results[tool_name] = self._run_tool(tool_name=tool_name, user_id=user_id, trace=trace)
            if plan.retrieval_needed and retrieval_result is None:
                retrieval_query = plan.retrieval_query or message
                retrieval_result = self._run_retrieval(retrieval_query, trace)

            evidence = self.evidence_builder.build(tool_results=tool_results, retrieval_result=retrieval_result)
            if plan.query_type != "COMPLEX_EXPLANATION":
                break
            if self.evidence_builder.is_sufficient_for_complex_explanation(evidence):
                trace.steps.append(
                    ExecutionStep(
                        name="evidence_check",
                        kind="compose",
                        status="completed",
                        detail="Tool and retrieval evidence were sufficient for grounded explanation.",
                        evidence=[item.title for item in evidence[:4]],
                    )
                )
                break
            if iteration + 1 >= plan.max_iterations:
                trace.steps.append(
                    ExecutionStep(
                        name="evidence_check",
                        kind="compose",
                        status="skipped",
                        detail="Reached bounded loop limit before expanding evidence further.",
                    )
                )

        evidence = self.evidence_builder.build(tool_results=tool_results, retrieval_result=retrieval_result)
        answer = self.response_composer.compose(
            plan=plan,
            user_message=message,
            tool_results=tool_results,
            retrieval_result=retrieval_result,
            evidence=evidence,
        )
        trace.steps.append(
            ExecutionStep(
                name="compose_response",
                kind="compose",
                status="completed",
                detail=f"Composed response from {len(evidence)} evidence items.",
                evidence=[item.title for item in evidence[:4]],
            )
        )
        response = self.response_composer.as_chat_response(plan=plan, answer=answer)

        trace.total_duration_ms = int((perf_counter() - started_at) * 1000)
        self._last_trace = trace
        logger.info(
            "agent_execution_completed trace_id=%s user_id=%s query_type=%s execution_mode=%s tool_calls=%s retrieval_used=%s retrieval_docs=%s duration_ms=%s",
            trace.trace_id,
            trace.user_id,
            trace.query_type,
            trace.execution_mode,
            trace.tool_calls,
            trace.retrieval_used,
            trace.retrieval_docs,
            trace.total_duration_ms,
        )
        return AgentExecutionResult(response=response, plan=plan, trace=trace)

    def get_last_trace(self) -> TraceContext | None:
        return self._last_trace

    def _run_tool(self, tool_name: str, user_id: str, trace: TraceContext) -> ToolResult:
        definition = self.tool_registry.get(tool_name)
        started_at = perf_counter()
        payload = definition.runner(user_id)
        duration_ms = int((perf_counter() - started_at) * 1000)
        evidence = definition.evidence_builder(payload)
        result = ToolResult(
            tool_name=tool_name,
            source=definition.source,
            payload=payload,
            payload_summary=", ".join(evidence) if evidence else tool_name,
            evidence=evidence,
        )
        trace.tool_calls.append(tool_name)
        trace.steps.append(
            ExecutionStep(
                name=tool_name,
                kind="tool",
                status="completed",
                detail=result.payload_summary,
                duration_ms=duration_ms,
                evidence=evidence,
            )
        )
        return result

    def _run_retrieval(self, query: str, trace: TraceContext) -> RetrievalResult:
        started_at = perf_counter()
        retrieval_result = self.rag_service.search_knowledge(query)
        duration_ms = int((perf_counter() - started_at) * 1000)
        trace.retrieval_used = retrieval_result.used
        trace.retrieval_docs = [document.doc_id for document in retrieval_result.documents]
        trace.steps.append(
            ExecutionStep(
                name="search_knowledge",
                kind="retrieval",
                status="completed" if retrieval_result.used else "skipped",
                detail="Knowledge snippets found." if retrieval_result.used else "No retrieval result passed threshold.",
                duration_ms=duration_ms,
                evidence=[document.title for document in retrieval_result.documents],
            )
        )
        return retrieval_result
