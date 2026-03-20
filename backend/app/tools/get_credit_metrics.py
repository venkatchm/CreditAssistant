from __future__ import annotations

from app.schemas.credit import CreditMetricsResponse
from app.services.metrics_service import MetricsService


def get_credit_metrics(service: MetricsService, user_id: str) -> CreditMetricsResponse:
    return CreditMetricsResponse(metrics=service.get_metrics(user_id))
