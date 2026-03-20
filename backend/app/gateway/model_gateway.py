from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel, Field

from app.schemas.chat import EvidenceItem, ExecutionPlan


class GeneratedAnswerPayload(BaseModel):
    message: str
    causes: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    suggested_actions: list[str] = Field(default_factory=list)


class ModelGateway(ABC):
    @abstractmethod
    def generate(
        self,
        plan: ExecutionPlan,
        user_message: str,
        evidence: list[EvidenceItem],
        tool_context: dict[str, object],
        retrieval_context: list[str],
    ) -> GeneratedAnswerPayload:
        raise NotImplementedError


class LocalModelGateway(ModelGateway):
    def generate(
        self,
        plan: ExecutionPlan,
        user_message: str,
        evidence: list[EvidenceItem],
        tool_context: dict[str, object],
        retrieval_context: list[str],
    ) -> GeneratedAnswerPayload:
        if plan.query_type == "GENERAL_KNOWLEDGE":
            message = retrieval_context[0] if retrieval_context else "The knowledge layer could not find a strong enough educational match yet."
            return GeneratedAnswerPayload(message=message, evidence=retrieval_context[:3])

        if plan.query_type == "COMPLEX_EXPLANATION":
            profile = tool_context.get("get_credit_profile")
            metrics = tool_context.get("get_credit_metrics")
            recommendations = tool_context.get("get_recommendations", [])
            causes: list[str] = []
            if profile is not None:
                causes.extend(profile.credit_report.score_factors[:3])
            if metrics is not None:
                causes.extend(metrics.key_drivers[:3])
            if any("payment" in item.detail.lower() or "delinquency" in item.detail.lower() for item in evidence):
                causes.insert(0, "Recent late payment activity is contributing to the score decline.")
            deduped_causes = _dedupe(causes)[:4]

            evidence_lines: list[str] = []
            if profile is not None:
                change = profile.credit_report.score_change_30d
                direction = f"up {change} points" if change > 0 else f"down {abs(change)} points" if change < 0 else "unchanged"
                evidence_lines.append(f"Score change over 30 days: {direction}")
            if metrics is not None:
                evidence_lines.append(f"Revolving utilization: {metrics.revolving_utilization:.1%}")
                evidence_lines.append(f"Hard inquiries in last 12 months: {metrics.total_hard_inquiries_12m}")
                if metrics.months_since_last_delinquency is not None:
                    evidence_lines.append(f"Last delinquency: {metrics.months_since_last_delinquency} months ago")
            evidence_lines.extend(f"{item.title} ({item.citation})" for item in evidence if item.source_kind == "retrieval")
            evidence_lines = evidence_lines[:6]
            suggested_actions = [
                getattr(item, "title", str(item))
                for item in recommendations[:3]
            ]
            if profile is not None and metrics is not None:
                score = profile.credit_report.score
                score_band = profile.credit_report.score_band.replace("_", " ").title()
                score_change = metrics.score_change_30d
                direction = f"up {score_change} points" if score_change > 0 else f"down {abs(score_change)} points" if score_change < 0 else "unchanged"
                message = (
                    f"Your latest credit score is {score} ({score_band}), {direction} over the last 30 days. "
                    f"{profile.credit_report.summary}"
                )
                if any("late" in item.detail.lower() or "delinquency" in item.detail.lower() for item in evidence):
                    message += " The strongest tool-grounded signal is recent payment trouble."
                return GeneratedAnswerPayload(
                    message=message,
                    causes=deduped_causes,
                    evidence=evidence_lines,
                    suggested_actions=suggested_actions,
                )

        return GeneratedAnswerPayload(message=user_message, evidence=[item.detail for item in evidence[:3]])


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for item in items:
        normalized = item.strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(item)
    return deduped
