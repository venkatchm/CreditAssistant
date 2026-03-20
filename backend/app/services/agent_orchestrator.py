from __future__ import annotations

from typing import Iterable

from app.schemas.chat import ChatCard, ChatExplanation, ChatResponse, ClassificationResult
from app.services.credit_service import CreditService
from app.services.inquiry_service import InquiryService
from app.services.metrics_service import MetricsService
from app.services.payment_history_service import PaymentHistoryService
from app.services.rag_service import RagService
from app.services.recommendation_service import RecommendationService
from app.tools.get_credit_metrics import get_credit_metrics
from app.tools.get_credit_profile import get_credit_profile
from app.tools.get_inquiries import get_inquiries
from app.tools.get_payment_history import get_payment_history
from app.tools.get_recommendations import get_recommendations


class AgentOrchestrator:
    def __init__(
        self,
        credit_service: CreditService,
        metrics_service: MetricsService,
        recommendation_service: RecommendationService,
        inquiry_service: InquiryService,
        payment_history_service: PaymentHistoryService,
        rag_service: RagService,
    ) -> None:
        self.credit_service = credit_service
        self.metrics_service = metrics_service
        self.recommendation_service = recommendation_service
        self.inquiry_service = inquiry_service
        self.payment_history_service = payment_history_service
        self.rag_service = rag_service

    def execute(self, user_id: str, message: str, analysis: ClassificationResult) -> ChatResponse:
        normalized_message = analysis.normalized_message

        if analysis.category == "SIMPLE_FACT":
            return self._handle_simple_fact(user_id, normalized_message)
        if analysis.category == "SIMPLE_RECOMMENDATION":
            return self._handle_simple_recommendation(user_id)
        if analysis.category == "GENERAL_KNOWLEDGE":
            return self._handle_general_knowledge(message)
        if analysis.category == "COMPLEX_EXPLANATION":
            return self._handle_complex_explanation(user_id, message)
        return ChatResponse(
            message="This request is not supported yet. Try asking about your credit score, score changes, recommendations, inquiries, payment history, or utilization.",
            cards=[],
            requires_disclaimer=False,
            category="UNSUPPORTED",
        )

    def _handle_simple_fact(self, user_id: str, normalized_message: str) -> ChatResponse:
        if "inquir" in normalized_message:
            inquiry_response = get_inquiries(self.inquiry_service, user_id)
            cards = [
                ChatCard(
                    type="inquiry",
                    title=inquiry.creditor,
                    description=f"{self._labelize(inquiry.inquiry_type)} inquiry on {inquiry.inquiry_date}",
                    metadata={"bureau": inquiry.bureau, "hard_inquiry": "Yes" if inquiry.is_hard else "No"},
                )
                for inquiry in inquiry_response.inquiries
            ]
            return ChatResponse(
                message=f"You have {len(inquiry_response.inquiries)} inquiries in your current synthetic report.",
                cards=cards,
                requires_disclaimer=True,
                category="SIMPLE_FACT",
            )

        if "payment history" in normalized_message or "payments" in normalized_message:
            payment_response = get_payment_history(self.payment_history_service, user_id)
            cards = [
                ChatCard(
                    type="payment_history",
                    title=item.month,
                    description=f"{self._labelize(item.status)} on {item.account_id}",
                    value=f"Paid {item.amount_paid} of {item.amount_due}",
                )
                for item in payment_response.payment_history[:6]
            ]
            return ChatResponse(
                message="Here is the latest payment history from your current synthetic report.",
                cards=cards,
                requires_disclaimer=True,
                category="SIMPLE_FACT",
            )

        if "utilization" in normalized_message:
            metrics_response = get_credit_metrics(self.metrics_service, user_id)
            metrics = metrics_response.metrics
            cards = [
                ChatCard(
                    type="utilization",
                    title="Revolving Utilization",
                    description="Percent of available revolving credit currently in use.",
                    value=f"{metrics.revolving_utilization:.1%}",
                ),
                ChatCard(
                    type="available_credit",
                    title="Available Credit",
                    value=f"${metrics.total_available_credit:,}",
                ),
            ]
            return ChatResponse(
                message=(
                    f"Your current revolving utilization is {metrics.revolving_utilization:.1%}, "
                    f"with ${metrics.total_available_credit:,} in available revolving credit."
                ),
                cards=cards,
                requires_disclaimer=True,
                category="SIMPLE_FACT",
            )

        profile = get_credit_profile(self.credit_service, user_id)
        factors = self._dedupe_texts(profile.metrics.key_drivers[:3] + profile.credit_report.score_factors[:2])
        cards = [
            ChatCard(
                type="credit_score",
                title="Credit Score",
                score=profile.credit_report.score,
                updated_at=profile.credit_report.generated_at,
                description=f"Score band: {self._labelize(profile.credit_report.score_band)}",
            )
        ]
        cards.extend(ChatCard(type="factor", title=self._factor_title(factor), description=factor) for factor in factors[:2])
        return ChatResponse(
            message=(
                f"Your latest credit score is {profile.credit_report.score} "
                f"({self._labelize(profile.credit_report.score_band)}). "
                f"{profile.credit_report.summary}"
            ),
            cards=cards,
            requires_disclaimer=True,
            category="SIMPLE_FACT",
        )

    def _handle_simple_recommendation(self, user_id: str) -> ChatResponse:
        recommendation_response = get_recommendations(self.recommendation_service, user_id)
        metrics = get_credit_metrics(self.metrics_service, user_id).metrics
        top_recommendations = recommendation_response.recommendations[:3]
        cards = [
            ChatCard(
                type="recommendation",
                title=item.title,
                description=item.action,
                priority=self._labelize(item.priority),
                metadata={"category": self._labelize(item.category), "impact": item.expected_impact},
            )
            for item in top_recommendations
        ]
        message = (
            f"Your latest credit score is {metrics.score}. "
            f"{top_recommendations[0].title if top_recommendations else 'Improving utilization and payment consistency'} "
            f"is the top recommendation for your current profile."
        )
        explanation = ChatExplanation(
            causes=[],
            evidence=[f"Current score: {metrics.score}", f"Revolving utilization: {metrics.revolving_utilization:.1%}"],
            suggested_actions=[item.title for item in top_recommendations],
        )
        return ChatResponse(
            message=message,
            cards=cards,
            requires_disclaimer=True,
            category="SIMPLE_RECOMMENDATION",
            explanation=explanation,
        )

    def _handle_general_knowledge(self, message: str) -> ChatResponse:
        docs = self.rag_service.search_knowledge(message)
        cards = [
            ChatCard(type="knowledge", title=doc["title"], description=doc["content"], metadata={"topic": doc["topic"]})
            for doc in docs
        ]
        message_text = "The knowledge layer could not find a strong match yet."
        if docs:
            message_text = docs[0]["content"]
        return ChatResponse(
            message=message_text,
            cards=cards,
            requires_disclaimer=True,
            category="GENERAL_KNOWLEDGE",
        )

    def _handle_complex_explanation(self, user_id: str, message: str) -> ChatResponse:
        profile = get_credit_profile(self.credit_service, user_id)
        metrics = get_credit_metrics(self.metrics_service, user_id).metrics
        inquiries = get_inquiries(self.inquiry_service, user_id).inquiries
        recommendations = get_recommendations(self.recommendation_service, user_id).recommendations
        knowledge_docs = self.rag_service.search_knowledge(message)

        causes = self._dedupe_texts([*profile.credit_report.score_factors, *metrics.key_drivers])
        evidence = [
            f"Score change over 30 days: {self._format_score_change(profile.credit_report.score_change_30d)}",
            f"Revolving utilization: {metrics.revolving_utilization:.1%}",
            f"Hard inquiries in last 12 months: {metrics.total_hard_inquiries_12m}",
        ]
        if metrics.months_since_last_delinquency is not None:
            evidence.append(f"Last delinquency: {metrics.months_since_last_delinquency} months ago")
        evidence.extend(doc["title"] for doc in knowledge_docs[:1])
        suggested_actions = [item.title for item in recommendations[:3]]

        cards = [
            ChatCard(
                type="credit_score",
                title="Credit Score",
                score=profile.credit_report.score,
                updated_at=profile.credit_report.generated_at,
                description=f"30-day change: {self._format_score_change(profile.credit_report.score_change_30d)}",
            )
        ]
        cards.extend(ChatCard(type="factor", title=self._factor_title(cause), description=cause) for cause in causes[:3])
        cards.extend(
            ChatCard(
                type="recommendation",
                title=item.title,
                description=item.action,
                priority=self._labelize(item.priority),
            )
            for item in recommendations[:2]
        )

        explanation = ChatExplanation(causes=causes[:4], evidence=evidence[:5], suggested_actions=suggested_actions)
        message_text = (
            f"Your latest credit score is {profile.credit_report.score} "
            f"({self._labelize(profile.credit_report.score_band)}), "
            f"{self._format_score_change(profile.credit_report.score_change_30d)} over the last 30 days. "
            f"{profile.credit_report.summary}"
        )
        if inquiries and metrics.total_hard_inquiries_12m > 0:
            message_text += f" Recent hard inquiries and balance levels are part of the current evidence."
        return ChatResponse(
            message=message_text,
            cards=cards,
            requires_disclaimer=True,
            category="COMPLEX_EXPLANATION",
            explanation=explanation,
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
