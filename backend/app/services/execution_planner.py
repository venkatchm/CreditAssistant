from __future__ import annotations

from app.schemas.chat import ClassificationResult, ExecutionPlan


class ExecutionPlanner:
    def build_plan(self, analysis: ClassificationResult, message: str) -> ExecutionPlan:
        normalized = analysis.normalized_message
        if analysis.category == "SIMPLE_FACT":
            tool_names = [self._fact_tool(normalized)]
            return ExecutionPlan(
                query_type="SIMPLE_FACT",
                execution_mode="FAST_FACT",
                steps=["query_analysis", *tool_names, "compose_response"],
                tool_names=tool_names,
                retrieval_needed=False,
                response_strategy="tool_only_fact_response",
                max_iterations=1,
            )
        if analysis.category == "SIMPLE_RECOMMENDATION":
            tool_names = ["get_recommendations", "get_credit_metrics"]
            return ExecutionPlan(
                query_type="SIMPLE_RECOMMENDATION",
                execution_mode="FAST_RECOMMENDATION",
                steps=["query_analysis", *tool_names, "compose_response"],
                tool_names=tool_names,
                retrieval_needed=False,
                response_strategy="tool_only_recommendation_response",
                max_iterations=1,
            )
        if analysis.category == "GENERAL_KNOWLEDGE":
            return ExecutionPlan(
                query_type="GENERAL_KNOWLEDGE",
                execution_mode="KNOWLEDGE_ONLY",
                steps=["query_analysis", "search_knowledge", "compose_response"],
                tool_names=[],
                retrieval_needed=True,
                retrieval_query=message,
                response_strategy="retrieval_only_knowledge_response",
                max_iterations=1,
            )
        if analysis.category == "COMPLEX_EXPLANATION":
            tool_names = ["get_credit_profile", "get_credit_metrics", "get_recommendations"]
            if self._contains_any(normalized, ["inquiry", "application", "hard pull", "hard inquiry", "score drop"]):
                tool_names.append("get_inquiries")
            if self._contains_any(normalized, ["late", "payment", "delinquency", "missed", "score drop"]):
                tool_names.append("get_payment_history")
            return ExecutionPlan(
                query_type="COMPLEX_EXPLANATION",
                execution_mode="COMPLEX_EXPLANATION",
                steps=["query_analysis", *tool_names, "search_knowledge", "evidence_check", "compose_response"],
                tool_names=tool_names,
                retrieval_needed=True,
                retrieval_query=self._build_complex_retrieval_query(message),
                response_strategy="tool_and_retrieval_grounded_explanation",
                max_iterations=2,
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

    def _fact_tool(self, normalized_message: str) -> str:
        if "inquir" in normalized_message:
            return "get_inquiries"
        if "payment history" in normalized_message or "payments" in normalized_message:
            return "get_payment_history"
        if "utilization" in normalized_message:
            return "get_credit_metrics"
        return "get_credit_profile"

    def _build_complex_retrieval_query(self, message: str) -> str:
        return f"{message} credit score drop payment history utilization hard inquiry"

    def _contains_any(self, normalized_message: str, terms: list[str]) -> bool:
        return any(term in normalized_message for term in terms)
