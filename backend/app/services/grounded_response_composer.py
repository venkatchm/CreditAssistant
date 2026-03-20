from __future__ import annotations

from typing import Iterable

from app.gateway.model_gateway import ModelGateway, ModelGatewayRequest
from app.schemas.chat import (
    ChatCard,
    ChatExplanation,
    ChatResponse,
    EvidenceItem,
    ExecutionPlan,
    GroundedAnswer,
    RetrievalResult,
    ToolResult,
)


class GroundedResponseComposer:
    def __init__(self, model_gateway: ModelGateway) -> None:
        self.model_gateway = model_gateway

    def compose(
        self,
        plan: ExecutionPlan,
        user_message: str,
        tool_results: dict[str, ToolResult],
        retrieval_result: RetrievalResult | None,
        evidence: list[EvidenceItem],
    ) -> GroundedAnswer:
        if plan.query_type == "SIMPLE_FACT":
            return self._compose_simple_fact(tool_results)
        if plan.query_type == "SIMPLE_RECOMMENDATION":
            return self._compose_recommendation(tool_results)
        if plan.query_type == "GENERAL_KNOWLEDGE":
            return self._compose_general_knowledge(plan, user_message, retrieval_result, evidence)
        if plan.query_type == "COMPLEX_EXPLANATION":
            return self._compose_complex_explanation(plan, user_message, tool_results, retrieval_result, evidence)
        return GroundedAnswer(
            message="This request is not supported yet. Try asking about your credit score, score changes, recommendations, inquiries, payment history, or utilization.",
            cards=[],
            evidence=evidence,
        )

    def _compose_simple_fact(self, tool_results: dict[str, ToolResult]) -> GroundedAnswer:
        if "get_inquiries" in tool_results:
            inquiries = tool_results["get_inquiries"].payload.inquiries
            source = tool_results["get_inquiries"].source
            cards = [
                ChatCard(
                    type="inquiry",
                    title=item.creditor,
                    description=f"{self._labelize(item.inquiry_type)} inquiry on {item.inquiry_date}",
                    metadata={"bureau": item.bureau, "hard_inquiry": "Yes" if item.is_hard else "No", "source": source},
                )
                for item in inquiries
            ]
            return GroundedAnswer(
                message=f"You have {len(inquiries)} inquiries in your current synthetic report.",
                cards=cards,
            )
        if "get_payment_history" in tool_results:
            history = tool_results["get_payment_history"].payload.payment_history
            source = tool_results["get_payment_history"].source
            cards = [
                ChatCard(
                    type="payment_history",
                    title=item.month,
                    description=f"{self._labelize(item.status)} on {item.account_id}",
                    value=f"Paid {item.amount_paid} of {item.amount_due}",
                    metadata={"source": source},
                )
                for item in history[:6]
            ]
            return GroundedAnswer(
                message="Here is the latest payment history from your current synthetic report.",
                cards=cards,
            )
        if "get_credit_metrics" in tool_results:
            metrics = tool_results["get_credit_metrics"].payload.metrics
            source = tool_results["get_credit_metrics"].source
            cards = [
                ChatCard(
                    type="utilization",
                    title="Revolving Utilization",
                    description="Percent of available revolving credit currently in use.",
                    value=f"{metrics.revolving_utilization:.1%}",
                    metadata={"source": source},
                ),
                ChatCard(
                    type="available_credit",
                    title="Available Credit",
                    value=f"${metrics.total_available_credit:,}",
                    metadata={"source": source},
                ),
            ]
            return GroundedAnswer(
                message=(
                    f"Your current revolving utilization is {metrics.revolving_utilization:.1%}, "
                    f"with ${metrics.total_available_credit:,} in available revolving credit."
                ),
                cards=cards,
            )
        profile = tool_results["get_credit_profile"].payload
        source = tool_results["get_credit_profile"].source
        factors = self._dedupe_texts(profile.metrics.key_drivers[:3] + profile.credit_report.score_factors[:2])
        cards = [
            ChatCard(
                type="credit_score",
                title="Credit Score",
                score=profile.credit_report.score,
                updated_at=profile.credit_report.generated_at,
                description=f"Score band: {self._labelize(profile.credit_report.score_band)}",
                metadata={"source": source},
            )
        ]
        cards.extend(ChatCard(type="factor", title=self._factor_title(factor), description=factor) for factor in factors[:2])
        return GroundedAnswer(
            message=(
                f"Your latest credit score is {profile.credit_report.score} "
                f"({self._labelize(profile.credit_report.score_band)}). "
                f"{profile.credit_report.summary}"
            ),
            cards=cards,
        )

    def _compose_recommendation(self, tool_results: dict[str, ToolResult]) -> GroundedAnswer:
        recommendation_result = tool_results["get_recommendations"]
        metrics = tool_results["get_credit_metrics"].payload.metrics
        top_recommendations = recommendation_result.payload.recommendations[:3]
        cards = [
            ChatCard(
                type="recommendation",
                title=item.title,
                description=item.action,
                priority=self._labelize(item.priority),
                metadata={
                    "category": self._labelize(item.category),
                    "impact": item.expected_impact,
                    "source": recommendation_result.source,
                },
            )
            for item in top_recommendations
        ]
        explanation = ChatExplanation(
            evidence=[f"Current score: {metrics.score}", f"Revolving utilization: {metrics.revolving_utilization:.1%}"],
            suggested_actions=[item.title for item in top_recommendations],
        )
        return GroundedAnswer(
            message=(
                f"Your latest credit score is {metrics.score}. "
                f"{top_recommendations[0].title if top_recommendations else 'Improving utilization and payment consistency'} "
                f"is the top recommendation for your current profile."
            ),
            cards=cards,
            explanation=explanation,
        )

    def _compose_general_knowledge(
        self,
        plan: ExecutionPlan,
        user_message: str,
        retrieval_result: RetrievalResult | None,
        evidence: list[EvidenceItem],
    ) -> GroundedAnswer:
        documents = retrieval_result.documents if retrieval_result else []
        generated = self.model_gateway.generate(
            ModelGatewayRequest(
                plan=plan,
                user_message=user_message,
                evidence=evidence,
                retrieval_context=[document.snippet for document in documents],
                grounding_rules=self._grounding_rules(),
            )
        )
        cards = [
            ChatCard(
                type="knowledge",
                title=document.title,
                description=document.snippet,
                metadata={
                    "topic": document.topic,
                    "source": document.source,
                    "confidence": f"{document.confidence:.2f}",
                },
            )
            for document in documents
        ]
        return GroundedAnswer(message=generated.message, cards=cards, evidence=evidence)

    def _compose_complex_explanation(
        self,
        plan: ExecutionPlan,
        user_message: str,
        tool_results: dict[str, ToolResult],
        retrieval_result: RetrievalResult | None,
        evidence: list[EvidenceItem],
    ) -> GroundedAnswer:
        profile = tool_results["get_credit_profile"].payload
        metrics = tool_results["get_credit_metrics"].payload.metrics
        recommendations = tool_results["get_recommendations"].payload.recommendations
        inquiries = tool_results.get("get_inquiries")
        payment_history = tool_results.get("get_payment_history")

        causes = self._dedupe_texts([*profile.credit_report.score_factors, *metrics.key_drivers])
        payment_entries = payment_history.payload.payment_history if payment_history else []
        if any(item.status != "on_time" for item in payment_entries):
            causes = self._dedupe_texts(["Recent late payment activity is contributing to the score decline.", *causes])

        retrieval_titles = [
            f"{document.title} ({document.source})"
            for document in (retrieval_result.documents if retrieval_result else [])[:2]
        ]
        evidence_lines = [
            f"Score change over 30 days: {self._format_score_change(profile.credit_report.score_change_30d)}",
            f"Revolving utilization: {metrics.revolving_utilization:.1%}",
            f"Hard inquiries in last 12 months: {metrics.total_hard_inquiries_12m}",
        ]
        if metrics.months_since_last_delinquency is not None:
            evidence_lines.append(f"Last delinquency: {metrics.months_since_last_delinquency} months ago")
        if payment_entries:
            recent_issue = next((item for item in reversed(payment_entries) if item.status != "on_time"), None)
            if recent_issue is not None:
                evidence_lines.append(f"Recent payment issue: {self._labelize(recent_issue.status)} in {recent_issue.month}")
        evidence_lines.extend(retrieval_titles)

        cards = [
            ChatCard(
                type="credit_score",
                title="Credit Score",
                score=profile.credit_report.score,
                updated_at=profile.credit_report.generated_at,
                description=f"30-day change: {self._format_score_change(profile.credit_report.score_change_30d)}",
                metadata={"source": tool_results["get_credit_profile"].source},
            )
        ]
        cards.extend(ChatCard(type="factor", title=self._factor_title(cause), description=cause) for cause in causes[:3])
        cards.extend(
            ChatCard(
                type="recommendation",
                title=item.title,
                description=item.action,
                priority=self._labelize(item.priority),
                metadata={"source": tool_results["get_recommendations"].source},
            )
            for item in recommendations[:2]
        )

        message = (
            f"Your latest credit score is {profile.credit_report.score} "
            f"({self._labelize(profile.credit_report.score_band)}), "
            f"{self._format_score_change(profile.credit_report.score_change_30d)} over the last 30 days. "
            f"{profile.credit_report.summary}"
        )
        if payment_entries and any(item.status != "on_time" for item in payment_entries):
            message += " The strongest tool-grounded signal is recent payment trouble."
        elif inquiries and inquiries.payload.inquiries and metrics.total_hard_inquiries_12m > 0:
            message += " Recent hard inquiries are also part of the grounded evidence."

        generated = self.model_gateway.generate(
            ModelGatewayRequest(
                plan=plan,
                user_message=user_message,
                evidence=evidence,
                tool_context={
                    "get_credit_profile": profile.model_dump(mode="json"),
                    "get_credit_metrics": metrics.model_dump(mode="json"),
                    "get_recommendations": [item.model_dump(mode="json") for item in recommendations],
                },
                retrieval_context=[document.snippet for document in (retrieval_result.documents if retrieval_result else [])],
                grounding_rules=self._grounding_rules(),
            )
        )
        explanation = ChatExplanation(
            causes=generated.causes or causes[:4],
            evidence=generated.evidence or evidence_lines[:6],
            suggested_actions=generated.suggested_actions or [item.title for item in recommendations[:3]],
        )
        return GroundedAnswer(message=generated.message or message, cards=cards, explanation=explanation, evidence=evidence)

    def as_chat_response(self, plan: ExecutionPlan, answer: GroundedAnswer) -> ChatResponse:
        return ChatResponse(
            message=answer.message,
            cards=answer.cards,
            requires_disclaimer=True if plan.query_type != "UNSUPPORTED" else False,
            category=plan.query_type,
            explanation=answer.explanation,
        )

    def build_gateway_request(
        self,
        plan: ExecutionPlan,
        user_message: str,
        tool_results: dict[str, ToolResult],
        retrieval_result: RetrievalResult | None,
        evidence: list[EvidenceItem],
    ) -> ModelGatewayRequest:
        recommendations = tool_results.get("get_recommendations")
        profile = tool_results.get("get_credit_profile")
        metrics = tool_results.get("get_credit_metrics")
        return ModelGatewayRequest(
            plan=plan,
            user_message=user_message,
            evidence=evidence,
            tool_context={
                "get_credit_profile": profile.payload.model_dump(mode="json") if profile else {},
                "get_credit_metrics": metrics.payload.metrics.model_dump(mode="json") if metrics else {},
                "get_recommendations": [item.model_dump(mode="json") for item in recommendations.payload.recommendations] if recommendations else [],
            },
            retrieval_context=[document.snippet for document in (retrieval_result.documents if retrieval_result else [])],
            grounding_rules=self._grounding_rules(),
        )

    def _dedupe_texts(self, texts: Iterable[str]) -> list[str]:
        deduped: list[str] = []
        normalized_seen: list[str] = []
        for text in texts:
            normalized = self._normalize_text(text)
            if not normalized:
                continue
            if any(normalized in seen or seen in normalized for seen in normalized_seen):
                continue
            normalized_seen.append(normalized)
            deduped.append(text)
        return deduped

    def _normalize_text(self, text: str) -> str:
        normalized = "".join(character.lower() for character in text if character.isalnum() or character.isspace())
        return " ".join(normalized.split())

    def _labelize(self, value: str) -> str:
        return value.replace("_", " ").title()

    def _format_score_change(self, score_change: int) -> str:
        if score_change > 0:
            return f"up {score_change} points"
        if score_change < 0:
            return f"down {abs(score_change)} points"
        return "unchanged"

    def _factor_title(self, factor: str) -> str:
        words = factor.rstrip(".").split()
        return " ".join(words[:4]).title()

    def _grounding_rules(self) -> list[str]:
        return [
            "Personal credit facts must come from tool results, not retrieved documents.",
            "Educational credit explanations may use retrieved documents.",
            "Do not make claims that are unsupported by provided evidence.",
            "Prefer concise, grounded explanations with actionable next steps.",
        ]
