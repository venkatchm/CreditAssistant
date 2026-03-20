from __future__ import annotations

from fastapi import HTTPException

from app.repositories.base import CreditRepository
from synthetic.models import CreditMetrics, CreditProfile, Recommendation


class CreditService:
    def __init__(self, repository: CreditRepository) -> None:
        self.repository = repository

    def get_credit_profile(self, user_id: str) -> CreditProfile:
        user = self.repository.get_user(user_id)
        report = self.repository.get_credit_report(user_id)
        metrics = self.repository.get_metrics(user_id)
        if not user or not report or not metrics:
            raise HTTPException(status_code=404, detail=f"Credit profile not found for user_id={user_id}")
        return CreditProfile(
            user=user,
            credit_report=report,
            credit_accounts=self.repository.list_credit_accounts(user_id),
            loan_accounts=self.repository.list_loan_accounts(user_id),
            inquiries=self.repository.list_inquiries(user_id),
            payment_history=self.repository.list_payment_history(user_id),
            metrics=metrics,
            recommendations=self.repository.list_recommendations(user_id),
        )

    def get_credit_metrics(self, user_id: str) -> CreditMetrics:
        metrics = self.repository.get_metrics(user_id)
        if not metrics:
            raise HTTPException(status_code=404, detail=f"Credit metrics not found for user_id={user_id}")
        return metrics

    def get_recommendations(self, user_id: str) -> list[Recommendation]:
        user = self.repository.get_user(user_id)
        if not user:
            raise HTTPException(status_code=404, detail=f"User not found for user_id={user_id}")
        return self.repository.list_recommendations(user_id)
