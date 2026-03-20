from __future__ import annotations

import logging
from time import perf_counter
from typing import Callable
from uuid import uuid4

from app.gateway.model_gateway import LocalModelGateway, ModelGatewayRequest
from app.schemas.chat import (
    AgentAction,
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
        tool_results, retrieval_result, _ = self._execute_action_loop(
            user_id=user_id,
            message=message,
            plan=plan,
            trace=trace,
        )

        evidence = self.evidence_builder.build(tool_results=tool_results, retrieval_result=retrieval_result)
        if plan.query_type == "COMPLEX_EXPLANATION":
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
            else:
                trace.steps.append(
                    ExecutionStep(
                        name="evidence_check",
                        kind="compose",
                        status="skipped",
                        detail="Reached bounded action loop without both tool and retrieval evidence.",
                    )
                )
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

    def build_gateway_request(
        self,
        user_id: str,
        message: str,
        analysis: ClassificationResult,
        emit_event: Callable[[str, dict[str, object]], None] | None = None,
    ) -> tuple[ModelGatewayRequest, ExecutionPlan]:
        plan = self.planner.build_plan(analysis=analysis, message=message)
        if emit_event is not None:
            emit_event(
                "plan",
                {
                    "query_type": plan.query_type,
                    "execution_mode": plan.execution_mode,
                    "tool_names": plan.tool_names,
                    "retrieval_needed": plan.retrieval_needed,
                    "max_iterations": plan.max_iterations,
                    "response_strategy": plan.response_strategy,
                },
            )
        tool_results, retrieval_result, trace = self._execute_action_loop(
            user_id=user_id,
            message=message,
            plan=plan,
            emit_event=emit_event,
        )
        evidence = self.evidence_builder.build(tool_results=tool_results, retrieval_result=retrieval_result)
        if emit_event is not None:
            emit_event(
                "compose",
                {
                    "query_type": plan.query_type,
                    "evidence_count": len(evidence),
                    "tool_calls": trace.tool_calls,
                    "retrieval_used": retrieval_result.used if retrieval_result is not None else False,
                },
            )
        return (
            self.response_composer.build_gateway_request(
                plan=plan,
                user_message=message,
                tool_results=tool_results,
                retrieval_result=retrieval_result,
                evidence=evidence,
            ),
            plan,
        )

    def _execute_action_loop(
        self,
        user_id: str,
        message: str,
        plan: ExecutionPlan,
        trace: TraceContext | None = None,
        emit_event: Callable[[str, dict[str, object]], None] | None = None,
    ) -> tuple[dict[str, ToolResult], RetrievalResult | None, TraceContext]:
        tool_results: dict[str, ToolResult] = {}
        retrieval_result: RetrievalResult | None = None
        working_trace = trace or self._stream_trace(plan, user_id)
        gateway = self._decision_gateway()
        payload = ModelGatewayRequest(plan=plan, user_message=message)
        max_steps = max(1, plan.max_iterations)
        retrieval_attempts = 0

        for _ in range(max_steps):
            action = gateway.decide_action(
                payload=payload,
                available_tools=plan.tool_names,
                completed_tools=list(tool_results.keys()),
                retrieval_done=retrieval_result is not None,
                retrieval_attempts=retrieval_attempts,
                last_retrieval_confidence=retrieval_result.top_confidence if retrieval_result is not None else 0.0,
            )
            working_trace.steps.append(
                ExecutionStep(
                    name=f"decide_{action.action}",
                    kind="compose",
                    status="completed",
                    detail=self._action_trace_detail(action=action, tool_results=tool_results, retrieval_result=retrieval_result),
                    evidence=list(tool_results.keys()) + ([retrieval_result.query] if retrieval_result is not None else []),
                )
            )
            if action.action == "tool_call" and action.tool_name:
                if emit_event is not None:
                    emit_event("tool_start", {"tool_name": action.tool_name, "reasoning": action.reasoning})
                tool_result = self._run_tool(tool_name=action.tool_name, user_id=user_id, trace=working_trace)
                tool_results[action.tool_name] = tool_result
                if emit_event is not None:
                    emit_event(
                        "tool_result",
                        {
                            "tool_name": action.tool_name,
                            "source": tool_result.source,
                            "summary": tool_result.payload_summary,
                            "evidence": tool_result.evidence,
                        },
                    )
                payload = self._refresh_gateway_payload(payload, tool_results, retrieval_result)
                continue
            if action.action == "retrieve":
                retrieval_query = action.query or plan.retrieval_query or message
                retrieval_attempts += 1
                if emit_event is not None:
                    emit_event(
                        "retrieval_start",
                        {"query": retrieval_query, "reasoning": action.reasoning, "attempt": retrieval_attempts},
                    )
                retrieval_result = self._run_retrieval(retrieval_query, working_trace)
                if emit_event is not None:
                    emit_event(
                        "retrieval_result",
                        {
                            "query": retrieval_result.query,
                            "used": retrieval_result.used,
                            "top_confidence": retrieval_result.top_confidence,
                            "document_titles": [document.title for document in retrieval_result.documents],
                            "attempt": retrieval_attempts,
                        },
                    )
                payload = self._refresh_gateway_payload(payload, tool_results, retrieval_result)
                continue
            if action.action == "insufficient_evidence":
                break
            break

        return tool_results, retrieval_result, working_trace

    def _refresh_gateway_payload(
        self,
        payload: ModelGatewayRequest,
        tool_results: dict[str, ToolResult],
        retrieval_result: RetrievalResult | None,
    ) -> ModelGatewayRequest:
        evidence = self.evidence_builder.build(tool_results=tool_results, retrieval_result=retrieval_result)
        return ModelGatewayRequest(
            plan=payload.plan,
            user_message=payload.user_message,
            conversation_history=payload.conversation_history,
            user_attributes=payload.user_attributes,
            evidence=evidence,
            tool_context={
                tool_name: result.payload.model_dump(mode="json") if hasattr(result.payload, "model_dump") else result.payload
                for tool_name, result in tool_results.items()
            },
            retrieval_context=[document.snippet for document in retrieval_result.documents] if retrieval_result else [],
            grounding_rules=payload.grounding_rules,
        )

    def _decision_gateway(self):
        gateway = self.response_composer.model_gateway
        if hasattr(gateway, "decide_action"):
            return gateway
        return LocalModelGateway()

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

    def _stream_trace(self, plan: ExecutionPlan, user_id: str) -> TraceContext:
        return TraceContext(
            trace_id=str(uuid4()),
            user_id=user_id,
            query_type=plan.query_type,
            execution_mode=plan.execution_mode,
            response_strategy=plan.response_strategy,
        )

    def _action_trace_detail(
        self,
        action: AgentAction,
        tool_results: dict[str, ToolResult],
        retrieval_result: RetrievalResult | None,
    ) -> str:
        completed_tools = ", ".join(tool_results.keys()) or "none"
        retrieval_state = "done" if retrieval_result is not None else "pending"
        target = action.tool_name or action.query or "final answer"
        if action.reasoning:
            return (
                f"Selected {action.action} for {target}. "
                f"Reasoning: {action.reasoning} "
                f"Completed tools: {completed_tools}. Retrieval: {retrieval_state}."
            )
        return f"Selected {action.action} for {target}. Completed tools: {completed_tools}. Retrieval: {retrieval_state}."
