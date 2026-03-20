from __future__ import annotations

from fastapi import HTTPException

from app.repositories.base import CreditRepository
from synthetic.models import CreditMetrics


class MetricsService:
    def __init__(self, repository: CreditRepository) -> None:
        self.repository = repository

    def get_metrics(self, user_id: str) -> CreditMetrics:
        metrics = self.repository.get_metrics(user_id)
        if not metrics:
            raise HTTPException(status_code=404, detail=f"Credit metrics not found for user_id={user_id}")
        return metrics
