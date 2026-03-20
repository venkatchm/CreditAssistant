from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from app.services.credit_service import CreditService
from app.services.inquiry_service import InquiryService
from app.services.metrics_service import MetricsService
from app.services.payment_history_service import PaymentHistoryService
from app.services.recommendation_service import RecommendationService
from app.tools.get_credit_metrics import get_credit_metrics
from app.tools.get_credit_profile import get_credit_profile
from app.tools.get_inquiries import get_inquiries
from app.tools.get_payment_history import get_payment_history
from app.tools.get_recommendations import get_recommendations


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    source: str
    runner: Callable[[str], Any]
    evidence_builder: Callable[[Any], list[str]]


class ToolRegistry:
    def __init__(
        self,
        credit_service: CreditService,
        metrics_service: MetricsService,
        recommendation_service: RecommendationService,
        inquiry_service: InquiryService,
        payment_history_service: PaymentHistoryService,
    ) -> None:
        self._tools = {
            "get_credit_profile": ToolDefinition(
                name="get_credit_profile",
                source="synthetic_json_repository",
                runner=lambda user_id: get_credit_profile(credit_service, user_id),
                evidence_builder=lambda payload: [
                    f"Score: {payload.credit_report.score}",
                    f"Score band: {payload.credit_report.score_band}",
                ],
            ),
            "get_credit_metrics": ToolDefinition(
                name="get_credit_metrics",
                source="synthetic_json_repository",
                runner=lambda user_id: get_credit_metrics(metrics_service, user_id),
                evidence_builder=lambda payload: [
                    f"Utilization: {payload.metrics.revolving_utilization:.1%}",
                    f"Score: {payload.metrics.score}",
                ],
            ),
            "get_recommendations": ToolDefinition(
                name="get_recommendations",
                source="synthetic_json_repository",
                runner=lambda user_id: get_recommendations(recommendation_service, user_id),
                evidence_builder=lambda payload: [f"Recommendations returned: {len(payload.recommendations)}"],
            ),
            "get_inquiries": ToolDefinition(
                name="get_inquiries",
                source="synthetic_json_repository",
                runner=lambda user_id: get_inquiries(inquiry_service, user_id),
                evidence_builder=lambda payload: [f"Inquiries returned: {len(payload.inquiries)}"],
            ),
            "get_payment_history": ToolDefinition(
                name="get_payment_history",
                source="synthetic_json_repository",
                runner=lambda user_id: get_payment_history(payment_history_service, user_id),
                evidence_builder=lambda payload: [f"Payment entries returned: {len(payload.payment_history)}"],
            ),
        }

    def get(self, tool_name: str) -> ToolDefinition:
        return self._tools[tool_name]

    def has_tool(self, tool_name: str) -> bool:
        return tool_name in self._tools
