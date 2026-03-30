from __future__ import annotations

from app.schemas.chat import ClassificationResult, ExecutionPlan


class ExecutionPlanner:
    def build_plan(self, analysis: ClassificationResult, message: str) -> ExecutionPlan:
        normalized = analysis.normalized_message
        if analysis.category == "SIMPLE_FACT":
            tool_names = self._fact_tools(normalized)
            return ExecutionPlan(
                query_type="SIMPLE_FACT",
                execution_mode="FAST_FACT",
                steps=["query_analysis", "agent_action_loop", "compose_response"],
                tool_names=tool_names,
                retrieval_needed=False,
                response_strategy="tool_only_fact_response",
                max_iterations=2,
            )
        if analysis.category == "SIMPLE_RECOMMENDATION":
            tool_names = ["get_recommendations", "get_credit_metrics"]
            return ExecutionPlan(
                query_type="SIMPLE_RECOMMENDATION",
                execution_mode="FAST_RECOMMENDATION",
                steps=["query_analysis", "agent_action_loop", "compose_response"],
                tool_names=tool_names,
                retrieval_needed=True,
                retrieval_query=message,
                response_strategy="tool_only_recommendation_response",
                max_iterations=3,
            )
        if analysis.category == "GENERAL_KNOWLEDGE":
            return ExecutionPlan(
                query_type="GENERAL_KNOWLEDGE",
                execution_mode="KNOWLEDGE_ONLY",
                steps=["query_analysis", "agent_action_loop", "compose_response"],
                tool_names=[],
                retrieval_needed=True,
                retrieval_query=message,
                response_strategy="retrieval_only_knowledge_response",
                max_iterations=3,
            )
        if analysis.category == "COMPLEX_EXPLANATION":
            tool_names = self._complex_explanation_tools(normalized)
            return ExecutionPlan(
                query_type="COMPLEX_EXPLANATION",
                execution_mode="COMPLEX_EXPLANATION",
                steps=["query_analysis", "agent_action_loop", "evidence_check", "compose_response"],
                tool_names=tool_names,
                retrieval_needed=True,
                retrieval_query=self._build_complex_retrieval_query(message),
                response_strategy="tool_and_retrieval_grounded_explanation",
                # The orchestrator now runs a single deterministic tool pass; this only bounds retrieval retries.
                max_iterations=3,
            )
        return ExecutionPlan(
            query_type="UNSUPPORTED",
            execution_mode="UNSUPPORTED",
            steps=["query_analysis", "compose_response"],
            tool_names=[],
            retrieval_needed=False,
            response_strategy="unsupported_fallback",
            max_iterations=1,
        )

    def _fact_tools(self, normalized_message: str) -> list[str]:
        if "inquir" in normalized_message:
            return ["get_inquiries"]
        if "payment history" in normalized_message or "payments" in normalized_message:
            return ["get_payment_history"]
        if "utilization" in normalized_message:
            return ["get_credit_metrics", "get_credit_profile"]
        return ["get_credit_profile", "get_credit_metrics"]

    def _complex_explanation_tools(self, normalized_message: str) -> list[str]:
        preferred: list[str] = ["get_credit_profile", "get_credit_metrics", "get_recommendations"]
        if self._contains_any(normalized_message, ["late", "payment", "delinquency", "missed", "score drop"]):
            preferred.append("get_payment_history")
        if self._contains_any(normalized_message, ["inquiry", "inquiries", "application", "hard pull", "hard inquiry"]):
            preferred.append("get_inquiries")
            if "get_payment_history" not in preferred:
                preferred.append("get_payment_history")
        if not any(tool_name in preferred for tool_name in ["get_payment_history", "get_inquiries"]):
            preferred.append("get_payment_history")
        ordered: list[str] = []
        for tool_name in preferred:
            if tool_name not in ordered:
                ordered.append(tool_name)
        return ordered

    def _build_complex_retrieval_query(self, message: str) -> str:
        return f"{message} credit score drop payment history utilization hard inquiry"

    def _contains_any(self, normalized_message: str, terms: list[str]) -> bool:
        return any(term in normalized_message for term in terms)
